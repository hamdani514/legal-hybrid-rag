/**
 * Session Timeout Manager
 * 
 * Enforces security & activity policy backed by both frontend and backend:
 * - 24 hours total session duration from login/extension.
 * - 1 minute (60 seconds) warning countdown before auto logout.
 * - Warning timer is displayed in a dedicated popup screen.
 * - Server Processing & Inactivity Protection:
 *   If user is actively scrolling, interacting, or if a backend query / API
 *   request is in-flight, the warning popup is suppressed and session is deferred
 *   until server response is complete and user has viewed the result.
 * - Closed-Tab Support:
 *   Validates JWT server exp & local expiry on tab reopen, purging if >24h elapsed.
 */

export const SESSION_TIMEOUT_SECONDS = 24 * 60 * 60; // 24 hours (86,400s)
export const WARNING_SECONDS = 60;                   // 1 minute before logout (60s)
export const SESSION_EXPIRES_KEY = 'sessionExpiresAt';
export const LAST_ACTIVITY_KEY = 'sessionLastActiveAt';

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

/**
 * Decode JWT expiration time (in ms) from token without external dependencies.
 */
export const getJwtExpiryMs = (token) => {
  if (!token || typeof token !== 'string') return null;
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const json = atob(base64);
    const payload = JSON.parse(json);
    return payload.exp ? Number(payload.exp) * 1000 : null;
  } catch {
    return null;
  }
};

/**
 * Check if a regular user is currently logged in.
 */
export const isUserLoggedIn = () => {
  try {
    const token = localStorage.getItem('authToken');
    const user = localStorage.getItem('currentUser');
    return Boolean(token && user);
  } catch {
    return false;
  }
};

/**
 * Check if an admin is currently logged in.
 */
export const isAdminLoggedIn = () => {
  try {
    const token = localStorage.getItem('adminAuthToken');
    const admin = localStorage.getItem('currentAdmin');
    return Boolean(token && admin);
  } catch {
    return false;
  }
};

/**
 * Check if either a user or an admin session is active.
 */
export const isAnySessionActive = () => {
  return isUserLoggedIn() || isAdminLoggedIn();
};

/**
 * Record user activity (scrolling, clicking, typing) to keep session fresh.
 * Throttled to once every 15 seconds to avoid performance overhead.
 */
let lastActivityRecorded = 0;
export const recordUserActivity = () => {
  const now = Date.now();
  if (now - lastActivityRecorded < 15000) return;
  lastActivityRecorded = now;

  try {
    if (!isAnySessionActive()) return;
    localStorage.setItem(LAST_ACTIVITY_KEY, String(now));
    
    // If less than 2 minutes remain and user is actively interacting, defer expiration
    const raw = localStorage.getItem(SESSION_EXPIRES_KEY);
    if (raw) {
      const expiresAt = Number(raw);
      if (expiresAt && expiresAt - now < 120000) {
        const deferred = now + 120000;
        localStorage.setItem(SESSION_EXPIRES_KEY, String(deferred));
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('session-timer-updated', { detail: { expiresAt: deferred } }));
        }
      }
    }
  } catch {
    /* ignore */
  }
};

/**
 * Initialize or start the 24-hour session timer.
 * Synchronizes with the backend JWT token's actual exp claim if present.
 */
export const initSessionTimeout = (explicitToken = null) => {
  try {
    const token = explicitToken || localStorage.getItem('authToken') || localStorage.getItem('adminAuthToken');
    const jwtExp = getJwtExpiryMs(token);
    const fallbackExp = Date.now() + SESSION_TIMEOUT_SECONDS * 1000;
    
    // Honor the earlier of the server JWT expiry or the 24-hour timeout
    const expiresAt = jwtExp && jwtExp > Date.now() ? Math.min(jwtExp, fallbackExp) : fallbackExp;

    localStorage.setItem(SESSION_EXPIRES_KEY, String(expiresAt));
    localStorage.setItem(LAST_ACTIVITY_KEY, String(Date.now()));
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('session-timer-updated', { detail: { expiresAt } }));
    }
    return expiresAt;
  } catch {
    return Date.now() + SESSION_TIMEOUT_SECONDS * 1000;
  }
};

/**
 * Extend the active session by another 24 hours.
 * Calls /api/auth/refresh to retrieve a fresh 24-hour JWT from the backend.
 */
export const extendSessionTimeout = async () => {
  const token = localStorage.getItem('authToken');
  if (token) {
    try {
      const res = await fetch('/api/auth/refresh', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });
      if (res.ok) {
        const data = await res.json();
        if (data?.token) {
          localStorage.setItem('authToken', data.token);
          return initSessionTimeout(data.token);
        }
      }
    } catch {
      /* network or server down, proceed with local extension */
    }
  }
  return initSessionTimeout();
};

/**
 * Clear the session timer from storage.
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
 * Get remaining seconds until session expiration.
 * Returns null if no active session or timer.
 */
export const getSessionRemainingSeconds = () => {
  try {
    const token = localStorage.getItem('authToken') || localStorage.getItem('adminAuthToken');
    const jwtExp = getJwtExpiryMs(token);
    const raw = localStorage.getItem(SESSION_EXPIRES_KEY);

    let expiresAt = raw ? Number(raw) : null;
    if (jwtExp) {
      expiresAt = expiresAt ? Math.min(expiresAt, jwtExp) : jwtExp;
    }

    if (!expiresAt || Number.isNaN(expiresAt)) return null;

    const remainingMs = expiresAt - Date.now();
    return Math.max(0, Math.ceil(remainingMs / 1000));
  } catch {
    return null;
  }
};

/**
 * Perform a clean, coordinated logout across user or admin roles.
 */
export const performLogout = ({ expired = false, navigate = null } = {}) => {
  const adminActive = isAdminLoggedIn();
  const userActive = isUserLoggedIn();

  clearSessionTimeout();

  try {
    if (adminActive && !userActive) {
      localStorage.removeItem('adminAuthToken');
      localStorage.removeItem('currentAdmin');
    } else {
      localStorage.removeItem('authToken');
      localStorage.removeItem('currentUser');
    }
  } catch {
    /* ignore */
  }

  // Notify components across tabs and within this tab
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('storage'));
    window.dispatchEvent(new Event('user-profile-updated'));
  }

  const targetPath = (adminActive && !userActive) ? '/admin-login' : '/login';
  const queryParam = expired ? '?expired=true' : '';
  const fullTarget = `${targetPath}${queryParam}`;

  if (typeof navigate === 'function') {
    navigate(fullTarget, { replace: true, state: { sessionExpired: expired } });
  } else if (typeof window !== 'undefined' && window.location.pathname !== targetPath) {
    window.location.assign(fullTarget);
  }
};

/**
 * Check if the active session has expired (either past local timeout or past JWT exp).
 * If expired and server is NOT currently processing a query, purges localStorage and redirects to login.
 * Returns true if valid active session, false if no session or expired.
 */
export const validateSessionOrPurge = ({ navigate = null } = {}) => {
  if (typeof window === 'undefined') return false;

  const userActive = isUserLoggedIn();
  const adminActive = isAdminLoggedIn();
  if (!userActive && !adminActive) return false;

  // If server is actively processing a query, do not purge yet
  if (isServerProcessing()) {
    return true;
  }

  const now = Date.now();
  const token = localStorage.getItem('authToken') || localStorage.getItem('adminAuthToken');
  const jwtExp = getJwtExpiryMs(token);
  const rawExpires = localStorage.getItem(SESSION_EXPIRES_KEY);
  const localExpires = rawExpires ? Number(rawExpires) : null;

  // If JWT expired on backend or local 24-hour timeout expired:
  const isServerExpired = jwtExp !== null && jwtExp <= now;
  const isLocalExpired = localExpires !== null && localExpires <= now;

  if (isServerExpired || isLocalExpired) {
    performLogout({ expired: true, navigate });
    return false;
  }

  return true;
};

// Immediate evaluation when the module is loaded in the browser.
if (typeof window !== 'undefined') {
  validateSessionOrPurge();

  // Attach global activity listeners for scrolling, clicking, and typing
  const onActivity = () => recordUserActivity();
  window.addEventListener('wheel', onActivity, { passive: true });
  window.addEventListener('scroll', onActivity, { passive: true });
  window.addEventListener('keydown', onActivity, { passive: true });
  window.addEventListener('mousedown', onActivity, { passive: true });
  window.addEventListener('touchstart', onActivity, { passive: true });
}
