/**
 * Toast notifications: short messages in the top-right corner.
 *
 *   toast.success('OTP sent to your email.')   green tick
 *   toast.error('Incorrect password.')         red cross
 *
 * Callable from anywhere — components, plain modules (api.js, sessionManager),
 * event handlers — because it is a tiny event bus, not React context. The
 * <Toaster /> mounted once in App.jsx renders whatever is emitted, and it sits
 * above the routes, so a toast survives the navigation that often follows it
 * ("Signed in" while moving to /welcome).
 *
 * The same message emitted twice within a moment (a double click, two effects)
 * shows once.
 */

const listeners = new Set();
let nextId = 1;
const recent = new Map(); // "type|message" -> time last shown

const DURATION_MS = { success: 4000, error: 6000 };
const DEDUPE_MS = 1500;

function emit(type, message, options = {}) {
  const text = typeof message === 'string' ? message.trim() : String(message ?? '').trim();
  if (!text) return null;
  const key = `${type}|${text}`;
  const now = Date.now();
  // dedupeMs: how long the same message stays quiet (longer for errors from a
  // list that polls, so an outage is one toast, not one per poll).
  if (now - (recent.get(key) || 0) < (options.dedupeMs ?? DEDUPE_MS)) return null;
  recent.set(key, now);
  const item = { id: nextId++, type, message: text, duration: options.duration ?? DURATION_MS[type] };
  listeners.forEach((listener) => listener(item));
  return item.id;
}

const PENDING_KEY = 'pendingToast';

export const toast = {
  success: (message, options) => emit('success', message, options),
  error: (message, options) => emit('error', message, options),
  /**
   * Show a toast after a full page load (window.location.assign), which would
   * otherwise wipe it: stored for this tab and shown by <Toaster /> on mount.
   */
  afterReload: (type, message) => {
    try {
      sessionStorage.setItem(PENDING_KEY, JSON.stringify({ type, message }));
    } catch {
      /* storage unavailable: the toast is skipped */
    }
  },
};

/** For <Toaster />: show a toast stored by toast.afterReload, once. */
export function flushPendingToast() {
  try {
    const raw = sessionStorage.getItem(PENDING_KEY);
    if (!raw) return;
    sessionStorage.removeItem(PENDING_KEY);
    const { type, message } = JSON.parse(raw);
    if (type === 'success' || type === 'error') emit(type, message);
  } catch {
    /* ignore */
  }
}

/** For <Toaster />: receive every toast as it is emitted. Returns an unsubscribe. */
export function subscribeToasts(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/**
 * The message to show for a failed response: the server's own `detail` when it
 * is a sentence, otherwise `fallback`. Reads a clone, so the caller can still
 * read the body itself.
 */
export async function errorMessage(res, fallback = 'Something went wrong. Please try again.') {
  try {
    const body = await res.clone().json();
    const detail = body?.detail ?? body?.message ?? body?.error;
    if (typeof detail === 'string' && detail.trim()) return detail.trim();
    // FastAPI validation errors: a list of {msg}
    if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
  } catch {
    /* not JSON */
  }
  return fallback;
}

export default toast;
