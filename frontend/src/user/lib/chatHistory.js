/**
 * Chat history client (POST/GET /api/chat/sessions...).
 *
 * Every call fails soft and returns a neutral value instead of throwing.
 * History is a convenience: if the server cannot store a conversation, the
 * research screen must still answer the question in front of the user.
 *
 * `userId` is the signed-in user's id (currentUser.id). The server prefers the
 * bearer token's subject when authentication is on and only falls back to this
 * value while it is off, so a conversation always belongs to one user.
 */

import apiFetch from '../../lib/api';

const BASE = '/api/chat/sessions';

const readJson = async (response) => {
  try {
    return await response.json();
  } catch {
    return null;
  }
};

const withUser = (url, userId) =>
  userId ? `${url}${url.includes('?') ? '&' : '?'}user_id=${encodeURIComponent(userId)}` : url;

const postJson = (url, body) =>
  apiFetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

/** Every conversation this user has, newest first. [] on any failure. */
export async function listSessions(userId) {
  try {
    const res = await apiFetch(withUser(BASE, userId));
    if (!res.ok) return [];
    const data = await readJson(res);
    return Array.isArray(data?.sessions) ? data.sessions : [];
  } catch {
    return [];
  }
}

/** Start a conversation; returns its id, or null if history is unavailable. */
export async function createSession(userId, title) {
  try {
    const res = await postJson(BASE, { user_id: userId, title: title || '' });
    if (!res.ok) return null;
    const data = await readJson(res);
    return data?.session_id || null;
  } catch {
    return null;
  }
}

/** One conversation's messages, exactly as they were on screen. null if gone. */
export async function loadSession(userId, sessionId) {
  try {
    const res = await apiFetch(withUser(`${BASE}/${encodeURIComponent(sessionId)}`, userId));
    if (!res.ok) return null;
    const data = await readJson(res);
    return Array.isArray(data?.messages) ? data : null;
  } catch {
    return null;
  }
}

/** Append messages to a conversation. Returns true when stored. */
export async function appendMessages(userId, sessionId, messages) {
  if (!sessionId || !messages?.length) return false;
  try {
    const res = await postJson(`${BASE}/${encodeURIComponent(sessionId)}/messages`, {
      user_id: userId,
      messages,
    });
    return res.ok;
  } catch {
    return false;
  }
}

const patchSession = async (userId, sessionId, fields) => {
  try {
    const res = await apiFetch(`${BASE}/${encodeURIComponent(sessionId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, ...fields }),
    });
    return res.ok;
  } catch {
    return false;
  }
};

/** Rename a conversation. Returns true on success. */
export const renameSession = (userId, sessionId, title) =>
  patchSession(userId, sessionId, { title });

/** Pin a conversation to the top of the list (or unpin it). */
export const setPinned = (userId, sessionId, pinned) =>
  patchSession(userId, sessionId, { pinned: !!pinned });

/** Delete one conversation. Returns true on success. */
export async function deleteSession(userId, sessionId) {
  try {
    const res = await apiFetch(withUser(`${BASE}/${encodeURIComponent(sessionId)}`, userId), {
      method: 'DELETE',
    });
    return res.ok;
  } catch {
    return false;
  }
}

/** Delete every conversation this user has. Returns true on success. */
export async function clearSessions(userId) {
  try {
    const res = await apiFetch(withUser(BASE, userId), { method: 'DELETE' });
    return res.ok;
  } catch {
    return false;
  }
}

/** "3 mins ago" for a server timestamp (stored UTC, serialised without a 'Z'). */
export const relativeTime = (value) => {
  if (!value) return '';
  const needsZ = typeof value === 'string' && !/[zZ]|[+-]\d{2}:?\d{2}$/.test(value);
  const then = new Date(needsZ ? `${value}Z` : value).getTime();
  if (Number.isNaN(then)) return '';
  const secs = Math.round((Date.now() - then) / 1000);
  if (secs < 60) return 'just now';
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins} min${mins > 1 ? 's' : ''} ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} hour${hours > 1 ? 's' : ''} ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} day${days > 1 ? 's' : ''} ago`;
  return new Date(then).toLocaleDateString();
};
