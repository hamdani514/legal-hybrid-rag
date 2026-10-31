/**
 * Session manager: who is signed in, and keeping them signed in.
 *
 * A session is the server-signed JWT the login screens stored (user:
 * "authToken" + "currentUser"; admin: "adminAuthToken" + "currentAdmin"). The
 * token's own `exp` is the only expiry: there is no separate local timer that
 * could log someone out while the server still accepts their token.
 *
 * Staying signed in
 * -----------------
 * A session renews itself silently: once half of a token's lifetime has
 * passed, POST /api/auth/refresh swaps it for a fresh one. That runs on page
 * load, when the tab regains focus, every minute while the app is open, and on
 * user activity — so someone using the app is never sent back to the login
 * page. Only a token that has really expired (the app was closed for longer
 * than the whole lifetime, JWT_EXPIRE_MINUTES on the server) needs a new login.
 *
 * User and admin sessions are separate: each is checked against its own token,
 * and an expired admin session never signs the user out (or the reverse).
 *
 * Signing out on a 401
 * --------------------
 * A 401 from some endpoint is not proof that the session is over (a handler
 * can refuse a request for its own reasons). confirmSessionEnded() asks the
 * refresh endpoint: only if the token itself is rejected is the session ended.
 */

import { toast } from './toast';

export const WARNING_SECONDS = 60;          // the "session ending" popup, for a session that cannot renew
export const SESSION_EXPIRES_KEY = 'sessionExpiresAt';   // mirror of the active token's exp, for the watcher
export const LAST_ACTIVITY_KEY = 'sessionLastActiveAt';

const USER_TOKEN = 'authToken';
const USER_PROFILE = 'currentUser';
const ADMIN_TOKEN = 'adminAuthToken';
const ADMIN_PROFILE = 'currentAdmin';

// Renew once less than this share of the token's lifetime is left.
const RENEW_WHEN_LEFT = 0.5;
// Do not try to renew the same session more often than this.
const RENEW_RETRY_MS = 60 * 1000;

const read = (key) => {
  try {
    return localStorage.getItem(key) || '';
  } catch {
    return '';
  }
};

/**
 * Check if the server is currently processing a query or API call.
 */
export const isServerProcessing = () => {
  if (typeof window === 'undefined') return false;
  return Boolean(
    (window.__activeApiCount && window.__activeApiCount > 0) ||
    window.__queryProcessing
  );
};

/** The claims of a JWT, decoded without verifying it (the server verifies). */
const jwtClaims = (token) => {
  if (!token || typeof token !== 'string') return null;
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(base64));
  } catch {
    return null;
  }
};

/**
 * Decode JWT expiration time (in ms) from token without external dependencies.
 */
export const getJwtExpiryMs = (token) => {
  const claims = jwtClaims(token);
  return claims?.exp ? Number(claims.exp) * 1000 : null;
};

/** True when a token is present and its exp has passed. */
const isExpired = (token) => {
  const exp = getJwtExpiryMs(token);
  return exp !== null && exp <= Date.now();
};

/**
 * Check if a regular user is currently logged in.
 */
export const isUserLoggedIn = () => Boolean(read(USER_TOKEN) && read(USER_PROFILE));

/**
 * Check if an admin is currently logged in.
 */
export const isAdminLoggedIn = () => Boolean(read(ADMIN_TOKEN) && read(ADMIN_PROFILE));

/**
 * Check if either a user or an admin session is active.
 */
export const isAnySessionActive = () => isUserLoggedIn() || isAdminLoggedIn();

/** A signed-in session of this role whose token has not expired. */
export const hasValidSession = (role = 'user') =>
  role === 'admin'
    ? isAdminLoggedIn() && !isExpired(read(ADMIN_TOKEN))
    : isUserLoggedIn() && !isExpired(read(USER_TOKEN));

/** Which session the current page belongs to: the admin pages, or everything else. */
export const currentArea = () =>
  typeof window !== 'undefined' && window.location.pathname.startsWith('/admin') ? 'admin' : 'user';

/** The token of the session that governs the current page. */
const areaToken = () => (currentArea() === 'admin' ? read(ADMIN_TOKEN) : read(USER_TOKEN));

// ── Renewal ────────────────────────────────────────────────────────────────

const lastRenewAttempt = { user: 0, admin: 0 };
const inFlight = { user: null, admin: null };

/**
 * Exchange a session's token for a fresh one. Resolves to:
 *   "renewed"  the server issued a new token (stored),
 *   "rejected" the server refused the token (401): the session is over,
 *   "unknown"  no answer (network, server down): nothing is changed.
 */
const renew = (role) => {
  if (inFlight[role]) return inFlight[role];
  const key = role === 'admin' ? ADMIN_TOKEN : USER_TOKEN;
  const token = read(key);
  if (!token) return Promise.resolve('rejected');
  lastRenewAttempt[role] = Date.now();
  inFlight[role] = (async () => {
    try {
      const res = await fetch('/api/auth/refresh', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      });
      if (res.status === 401) return 'rejected';
      if (!res.ok) return 'unknown';
      const data = await res.json();
      if (!data?.token) return 'unknown';
      // Only replace the token that was renewed: a login or logout meanwhile wins.
      if (read(key) === token) {
        localStorage.setItem(key, data.token);
        initSessionTimeout();
      }
      return 'renewed';
    } catch {
      return 'unknown';
    } finally {
      inFlight[role] = null;
    }
  })();
  return inFlight[role];
};

/** Renew each signed-in session whose token is past half of its lifetime. */
export const refreshSessionIfNeeded = () => {
  for (const role of ['user', 'admin']) {
    const token = read(role === 'admin' ? ADMIN_TOKEN : USER_TOKEN);
    const claims = jwtClaims(token);
    if (!claims?.exp) continue;
    const exp = Number(claims.exp) * 1000;
    const iat = claims.iat ? Number(claims.iat) * 1000 : exp - 24 * 60 * 60 * 1000;
    const now = Date.now();
    if (exp <= now) continue;   // already over: renewal cannot help
    if (exp - now > (exp - iat) * RENEW_WHEN_LEFT) continue;
    if (now - lastRenewAttempt[role] < RENEW_RETRY_MS) continue;
    renew(role);
  }
};

/**
 * After a 401: is the session really over? Asks the refresh endpoint, which
 * rejects only an invalid or expired token. Resolves true only then.
 */
export const confirmSessionEnded = async ({ admin = false } = {}) =>
  (await renew(admin ? 'admin' : 'user')) === 'rejected';

/**
 * Record user activity (scrolling, clicking, typing). Throttled; activity is
 * a moment to renew a session that is getting old.
 */
let lastActivityRecorded = 0;
export const recordUserActivity = () => {
  const now = Date.now();
  if (now - lastActivityRecorded < 15000) return;
  lastActivityRecorded = now;
  try {
    if (!isAnySessionActive()) return;
    localStorage.setItem(LAST_ACTIVITY_KEY, String(now));
    refreshSessionIfNeeded();
  } catch {
    /* ignore */
  }
};

// ── The watcher's view of the session ──────────────────────────────────────

/**
 * Mirror the current page's token expiry for the watcher. Called after every
 * login and renewal; the token's exp is the only expiry.
 */
export const initSessionTimeout = (explicitToken = null) => {
  const token = explicitToken || areaToken() || read(USER_TOKEN) || read(ADMIN_TOKEN);
  const expiresAt = getJwtExpiryMs(token) || Date.now() + 24 * 60 * 60 * 1000;
  try {
    localStorage.setItem(SESSION_EXPIRES_KEY, String(expiresAt));
    localStorage.setItem(LAST_ACTIVITY_KEY, String(Date.now()));
  } catch {
    /* ignore */
  }
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('session-timer-updated', { detail: { expiresAt } }));
  }
  return expiresAt;
};

/**
 * "Stay signed in": renew the current page's session now.
 */
export const extendSessionTimeout = async () => {
  await renew(currentArea());
  return initSessionTimeout();
};

/**
 * Clear the session mirror from storage.
 */
export const clearSessionTimeout = () => {
  try {
    localStorage.removeItem(SESSION_EXPIRES_KEY);
    localStorage.removeItem(LAST_ACTIVITY_KEY);
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('session-timer-cleared'));
    }
  } catch {
    /* ignore */
  }
};

/**
 * Seconds until the current page's session expires; null when signed out.
 */
export const getSessionRemainingSeconds = () => {
  const exp = getJwtExpiryMs(areaToken());
  if (!exp) return null;
  return Math.max(0, Math.ceil((exp - Date.now()) / 1000));
};

// ── Signing out ────────────────────────────────────────────────────────────

const purge = (role) => {
  try {
    if (role === 'admin') {
      localStorage.removeItem(ADMIN_TOKEN);
      localStorage.removeItem(ADMIN_PROFILE);
    } else {
      localStorage.removeItem(USER_TOKEN);
      localStorage.removeItem(USER_PROFILE);
    }
    if (!read(USER_TOKEN) && !read(ADMIN_TOKEN)) clearSessionTimeout();
  } catch {
    /* ignore */
  }
};

/**
 * Sign one session out (by default the current page's) and go to its login page.
 */
export const performLogout = ({ expired = false, navigate = null, role = null } = {}) => {
  const which = role || currentArea();
  purge(which);

  // Notify components across tabs and within this tab
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('storage'));
    window.dispatchEvent(new Event('user-profile-updated'));
  }

  const targetPath = which === 'admin' ? '/admin-login' : '/login';
  const fullTarget = `${targetPath}`;
  const notice = 'Your session has ended. Please sign in again.';

  if (typeof navigate === 'function') {
    if (expired) toast.error(notice);
    navigate(fullTarget, { replace: true, state: { sessionExpired: expired } });
  } else if (typeof window !== 'undefined' && window.location.pathname !== targetPath) {
    if (expired) toast.afterReload('error', notice);
    window.location.assign(fullTarget);
  }
};

/**
 * Is the current page's session valid? An expired session of the OTHER role is
 * cleared quietly; an expired session of this page's role signs out and goes to
 * its login page. Returns true when this page's session is valid.
 */
export const validateSessionOrPurge = ({ navigate = null } = {}) => {
  if (typeof window === 'undefined') return false;

  const area = currentArea();
  const other = area === 'admin' ? 'user' : 'admin';
  if (isExpired(read(other === 'admin' ? ADMIN_TOKEN : USER_TOKEN))) purge(other);

  const signedIn = area === 'admin' ? isAdminLoggedIn() : isUserLoggedIn();
  if (!signedIn) return false;

  // A query in flight finishes first; its own response decides.
  if (isServerProcessing()) return true;

  if (isExpired(area === 'admin' ? read(ADMIN_TOKEN) : read(USER_TOKEN))) {
    performLogout({ expired: true, navigate, role: area });
    return false;
  }
  return true;
};

// Immediate evaluation when the module is loaded in the browser.
if (typeof window !== 'undefined') {
  validateSessionOrPurge();
  refreshSessionIfNeeded();

  // Attach global activity listeners for scrolling, clicking, and typing
  const onActivity = () => recordUserActivity();
  window.addEventListener('wheel', onActivity, { passive: true });
  window.addEventListener('scroll', onActivity, { passive: true });
  window.addEventListener('keydown', onActivity, { passive: true });
  window.addEventListener('mousedown', onActivity, { passive: true });
  window.addEventListener('touchstart', onActivity, { passive: true });
}
