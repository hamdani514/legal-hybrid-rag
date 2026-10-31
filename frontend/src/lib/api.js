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
 *   - A 401 signs the session out only when the server confirms the token
 *     itself is no longer valid (sessionManager.confirmSessionEnded). Any other
 *     401 is returned to the caller like an ordinary error, and the user stays
 *     signed in. The response is always returned, so callers keep their own
 *     error handling.
 *   - A 429 is returned untouched: it means a rate limit (per user, or the
 *     shared Gemini budget), which the caller shows as "busy, try again".
 */

import {
  clearSessionTimeout,
  confirmSessionEnded,
  initSessionTimeout,
  performLogout,
} from './sessionManager';

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
    initSessionTimeout();
  } catch {
    /* storage unavailable: requests go out unauthenticated */
  }
};

export const clearToken = ({ admin = false } = {}) => {
  try {
    localStorage.removeItem(admin ? ADMIN_TOKEN_KEY : TOKEN_KEY);
    clearSessionTimeout();
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

  if (typeof window !== 'undefined') {
    window.__activeApiCount = (window.__activeApiCount || 0) + 1;
    window.dispatchEvent(new Event('api-activity-started'));
  }

  try {
    const response = await fetch(url, { ...options, headers });

    // Sign out only if the session itself is over. If it is still valid (or
    // the server cannot say), the caller just sees this request's 401.
    const key = admin ? ADMIN_TOKEN_KEY : TOKEN_KEY;
    if (response.status === 401 && token && readToken(key) === token) {
      if (await confirmSessionEnded({ admin })) {
        performLogout({ expired: true, role: admin ? 'admin' : 'user' });
        return response;
      }
      // The check renewed the token: send the request once more with it.
      const renewed = readToken(key);
      if (renewed && renewed !== token) {
        headers.set('Authorization', `Bearer ${renewed}`);
        return await fetch(url, { ...options, headers });
      }
    }

    return response;
  } finally {
    if (typeof window !== 'undefined') {
      window.__activeApiCount = Math.max(0, (window.__activeApiCount || 1) - 1);
      window.dispatchEvent(new Event('api-activity-ended'));
    }
  }
}

export default apiFetch;
