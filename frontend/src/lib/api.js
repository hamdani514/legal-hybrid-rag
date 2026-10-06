/**
 * The one way the frontend talks to the backend.
 *
 * Every request goes through apiFetch so authentication is added in exactly one
 * place. Two agents switch the app over to it in parallel — the security agent
 * (login, admin pages, forms) and the runtime agent (the research workspace) —
 * and this shared helper is what lets them do that without editing each
 * other's files.
 *
 * Contract:
 *   - The bearer token lives in localStorage under TOKEN_KEY ("authToken"),
 *     written by the login screens. Admin sessions use ADMIN_TOKEN_KEY.
 *   - Requests to /api/admin/* send the admin token; everything else sends the
 *     user token. A request with no token is still sent — the backend decides,
 *     and while AUTH_REQUIRED is off it accepts anonymous calls.
 *   - A 401 clears the stale token and sends the user to the right login page.
 *     The response is still returned, so callers keep their own error handling.
 *   - A 429 is returned untouched: it means a rate limit (per user, or the
 *     shared Gemini budget), which the caller shows as "busy, try again".
 */

export const TOKEN_KEY = 'authToken';
export const ADMIN_TOKEN_KEY = 'adminAuthToken';

const isAdminPath = (url) => String(url).includes('/api/admin');

const readToken = (key) => {
  try {
    return localStorage.getItem(key) || '';
  } catch {
    return '';
  }
};

export const setToken = (token, { admin = false } = {}) => {
  try {
    localStorage.setItem(admin ? ADMIN_TOKEN_KEY : TOKEN_KEY, token);
  } catch {
    /* storage unavailable: requests go out unauthenticated */
  }
};

export const clearToken = ({ admin = false } = {}) => {
  try {
    localStorage.removeItem(admin ? ADMIN_TOKEN_KEY : TOKEN_KEY);
  } catch {
    /* nothing to clear */
  }
};

/**
 * fetch() with the right bearer token attached.
 *
 * @param {string} url
 * @param {RequestInit} [options]
 * @returns {Promise<Response>}
 */
export async function apiFetch(url, options = {}) {
  const admin = isAdminPath(url);
  const token = readToken(admin ? ADMIN_TOKEN_KEY : TOKEN_KEY);

  const headers = new Headers(options.headers || {});
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(url, { ...options, headers });

  if (response.status === 401 && token) {
    clearToken({ admin });
    if (!admin) {
      try {
        localStorage.removeItem('currentUser');
      } catch {
        /* ignore */
      }
    }
    const target = admin ? '/admin-login' : '/login';
    if (typeof window !== 'undefined' && window.location.pathname !== target) {
      window.location.assign(target);
    }
  }

  return response;
}

export default apiFetch;
