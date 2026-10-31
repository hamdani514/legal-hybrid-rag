import { useEffect, useSyncExternalStore } from 'react';
import { paymentStatus } from './payments';

/**
 * The signed-in user's plan, and which research tools it unlocks.
 *
 * The server is the authority: backend/modules/payment/plans.py defines the
 * plans, every paid route checks them, and /api/payments/status and each
 * search response report the plan and its features. PLANS below mirrors that
 * table only so the UI has something sensible to show before the first answer
 * arrives. If they ever disagree the server wins: a locked route returns 403,
 * and the UI then shows the upgrade prompt.
 */

export const FEATURES = ['analyse', 'summarize', 'compare', 'download', 'filter', 'see_all', 'copy'];

export const FEATURE_LABELS = {
  analyse: 'Case analysis',
  summarize: 'Judgment summaries',
  compare: 'Comparing judgments',
  download: 'Downloading judgments',
  filter: 'Filtering results',
  see_all: 'Every relevant judgment',
  copy: 'Copying text',
};

const all = (on) => Object.fromEntries(FEATURES.map((f) => [f, on]));

export const PLANS = {
  free: { key: 'free', name: 'Free', dailyLimit: 2, maxResults: 10, price: 0, features: all(false) },
  standard: { key: 'standard', name: 'Standard', dailyLimit: 20, maxResults: null, price: 10, features: all(true) },
  premium: { key: 'premium', name: 'Premium', dailyLimit: 50, maxResults: null, price: 20, features: all(true) },
};

/** "Standard", "pro", "premium", undefined… → "free" | "standard" | "premium". */
export const planKey = (raw) => {
  const value = String(raw || '').trim().toLowerCase();
  if (value === 'premium') return 'premium';
  if (value === 'standard' || value === 'pro' || value === 'advocate') return 'standard';
  return 'free';
};

const storedPlan = () => {
  try {
    const user = JSON.parse(localStorage.getItem('currentUser') || 'null');
    return planKey(user?.plan || user?.user?.plan);
  } catch {
    return 'free';
  }
};

const build = (key, features, extra = {}) => ({
  ...PLANS[key],
  features: { ...PLANS[key].features, ...(features || {}) },
  ...extra,
});

let state = build(storedPlan(), null, { confirmed: false });
let loading = null;
const listeners = new Set();

const emit = () => listeners.forEach((listener) => listener());

/** Keep the stored user's plan label in step, for the nav and sidebar badges. */
const rememberPlanName = (name) => {
  try {
    const user = JSON.parse(localStorage.getItem('currentUser') || 'null');
    if (user && user.plan !== name) {
      localStorage.setItem('currentUser', JSON.stringify({ ...user, plan: name }));
      // SiteNav and the other headers re-read the stored user on this event
      // ('storage' fires only in other tabs), so the badge changes at once.
      window.dispatchEvent(new Event('user-profile-updated'));
    }
  } catch {
    /* storage unavailable: the badge just lags */
  }
};

/** Apply what the server said about the plan (status or a search response). */
export const setPlanFromServer = (key, features, extra = {}) => {
  if (!key) return;
  const k = planKey(key);
  state = build(k, features, { confirmed: true, ...extra });
  rememberPlanName(PLANS[k].name);
  emit();
};

/** Ask the server again — after a 403, a payment or a plan change. */
export const refreshPlan = async () => {
  if (!loading) {
    loading = paymentStatus()
      .then((status) => {
        if (status?.plan) {
          setPlanFromServer(status.plan, status.features, {
            used: status.dailyQueriesUsed,
            limit: status.dailyQueriesLimit,
          });
        }
      })
      .finally(() => {
        loading = null;
      });
  }
  return loading;
};

const subscribe = (listener) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

/**
 * The current plan: { key, name, dailyLimit, maxResults, features, confirmed }.
 * The first component to use it asks the server once.
 */
export const usePlan = () => {
  const plan = useSyncExternalStore(subscribe, () => state);
  useEffect(() => {
    if (!state.confirmed) refreshPlan();
  }, []);
  return plan;
};

/** The structured 403 a locked feature returns, or null. */
export const upgradeDetail = async (res) => {
  if (res.status !== 403) return null;
  try {
    const body = await res.clone().json();
    return body?.detail && typeof body.detail === 'object' && body.detail.requiresUpgrade ? body.detail : null;
  } catch {
    return null;
  }
};
