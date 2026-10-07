/**
 * Stripe Checkout client.
 *
 * The card is never typed into this app: the server creates a Checkout
 * session and we hand the browser to Stripe's hosted page. The plan is not
 * upgraded here either — Stripe's signed webhook does that, so closing the
 * tab mid-payment cannot leave an account wrongly upgraded, and a successful
 * payment still lands even if the browser never returns.
 */

import apiFetch from '../../lib/api';

/** The signed-in user, as the login screens stored them. */
export const currentUser = () => {
  try {
    return JSON.parse(localStorage.getItem('currentUser') || 'null');
  } catch {
    return null;
  }
};

/** The id the server keys plans by (falls back to email for older sessions). */
export const currentUserId = () => {
  const u = currentUser();
  return u?.id || u?.user?.id || u?.email || u?.user?.email || '';
};

const readJson = async (res) => {
  try {
    return await res.json();
  } catch {
    return null;
  }
};

/** Whether payments are configured, and in which mode. {} on failure. */
export async function paymentConfig() {
  try {
    const res = await apiFetch('/api/payments/config');
    return res.ok ? (await readJson(res)) || {} : {};
  } catch {
    return {};
  }
}

/**
 * Settle the payment the browser has just returned from.
 *
 * The webhook is the primary path, but it only fires where Stripe can reach
 * the server. This asks our backend to verify the session with Stripe
 * directly, so a real payment is applied even on localhost.
 */
export async function confirmCheckout(sessionId) {
  const id = currentUserId();
  if (!id || !sessionId) return null;
  try {
    const res = await apiFetch('/api/payments/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, user_id: id }),
    });
    return res.ok ? await readJson(res) : null;
  } catch {
    return null;
  }
}

/** The caller's plan as the SERVER sees it. null when it cannot be read. */
export async function paymentStatus() {
  const id = currentUserId();
  if (!id) return null;
  try {
    const res = await apiFetch(`/api/payments/status?user_id=${encodeURIComponent(id)}`);
    return res.ok ? await readJson(res) : null;
  } catch {
    return null;
  }
}

/**
 * Begin a subscription.
 *
 * Resolves to { ok: true } only after the browser has been sent to Stripe;
 * otherwise { ok: false, reason, message } so the caller can show the
 * server's own words rather than a generic failure.
 */
export async function startCheckout() {
  const id = currentUserId();
  if (!id) return { ok: false, reason: 'signin', message: 'Please sign in first.' };

  let res;
  try {
    res = await apiFetch('/api/payments/create-checkout-session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: id }),
    });
  } catch {
    return { ok: false, reason: 'network', message: 'Could not reach the payment service.' };
  }

  const data = (await readJson(res)) || {};
  if (res.status === 401) return { ok: false, reason: 'signin', message: 'Please sign in first.' };
  if (!res.ok) {
    return {
      ok: false,
      reason: res.status === 400 ? 'already' : 'error',
      message: typeof data.detail === 'string' ? data.detail : 'Could not start the payment.',
    };
  }
  if (!data.url) return { ok: false, reason: 'error', message: 'No checkout link was returned.' };

  // Leave the app for Stripe's hosted page.
  window.location.assign(data.url);
  return { ok: true };
}
