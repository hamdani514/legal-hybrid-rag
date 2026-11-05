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

export const PENDING_CHECKOUT_KEY = 'pendingCheckout';

/** The plan the last checkout was opened for, if it was opened in the last day. */
export const pendingCheckoutPlan = () => {
  try {
    const pending = JSON.parse(localStorage.getItem(PENDING_CHECKOUT_KEY) || 'null');
    return pending && Date.now() - pending.at < 24 * 3600 * 1000 ? pending.plan : null;
  } catch {
    return null;
  }
};

/** The signed-in user, as the login screens stored them. */
export const currentUser = () => {
  try {
    return JSON.parse(localStorage.getItem('currentUser') || 'null');
  } catch {
    return null;
  }
};

/** Whether someone is signed in. The server identifies them by their token. */
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
      body: JSON.stringify({ session_id: sessionId }),
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
    const res = await apiFetch('/api/payments/status');
    return res.ok ? await readJson(res) : null;
  } catch {
    return null;
  }
}

/**
 * Subscribe to a paid plan: "standard" ($10/month) or "premium" ($20/month).
 *
 * Switching between the two paid plans uses the same Checkout page; the
 * server cancels the old subscription once the new one is paid.
 *
 * Resolves to { ok: true } after the browser has been sent to Stripe;
 * otherwise { ok: false, reason, message } so the caller can show the
 * server's own words rather than a generic failure.
 */
export async function startCheckout(plan = 'standard') {
  const id = currentUserId();
  if (!id) return { ok: false, reason: 'signin', message: 'Please sign in first.' };

  let res;
  try {
    res = await apiFetch('/api/payments/create-checkout-session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan }),
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

  // Remembered for the success page, which must not say "payment successful"
  // until the account actually shows THIS plan (a switch starts from a paid one).
  try {
    localStorage.setItem(PENDING_CHECKOUT_KEY, JSON.stringify({ plan, at: Date.now() }));
  } catch {
    /* the success page then falls back to the server's word */
  }
  // Leave the app for Stripe's hosted page.
  window.location.assign(data.url);
  return { ok: true };
}

/**
 * Cancel active subscription at period end.
 */
export async function cancelSubscription() {
  const id = currentUserId();
  if (!id) return { ok: false, message: 'Please sign in first.' };

  try {
    const res = await apiFetch('/api/payments/cancel-subscription', { method: 'POST' });
    const data = await readJson(res);
    if (!res.ok) {
      return { ok: false, message: data?.detail || 'Could not cancel subscription.' };
    }
    return { ok: true, data, message: data?.message || 'Subscription cancelled.' };
  } catch {
    return { ok: false, message: 'Network error communicating with payment service.' };
  }
}

/**
 * Reactivate a subscription that was scheduled for cancellation.
 */
export async function reactivateSubscription() {
  const id = currentUserId();
  if (!id) return { ok: false, message: 'Please sign in first.' };

  try {
    const res = await apiFetch('/api/payments/reactivate-subscription', { method: 'POST' });
    const data = await readJson(res);
    if (!res.ok) {
      return { ok: false, message: data?.detail || 'Could not reactivate subscription.' };
    }
    return { ok: true, data, message: data?.message || 'Subscription reactivated.' };
  } catch {
    return { ok: false, message: 'Network error communicating with payment service.' };
  }
}
