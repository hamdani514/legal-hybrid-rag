import { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { FEATURE_LABELS, PLANS } from '../lib/plan';

/**
 * A research tool the user's plan does not include.
 *
 * It stays where the working tool would be, with the same label and icon, so
 * Free users learn the tool exists and where it lives. It is not `disabled`:
 * a disabled button cannot be focused or clicked, which leaves a keyboard user
 * with no way to find out why. Instead it looks inactive (dashed outline,
 * muted text, a lock badge) and opens the upgrade dialog that explains it.
 */
export const LockedButton = ({ feature, icon, label, onLocked, size = 'md', compact = false }) => {
  const small = size === 'sm';
  return (
    <button
      type="button"
      onClick={() => onLocked(feature)}
      aria-haspopup="dialog"
      aria-label={`${label}. Locked: available on the Standard and Premium plans.`}
      title="Available on the Standard and Premium plans"
      className={`group inline-flex items-center gap-1.5 rounded-full border border-dashed border-ash-300 bg-ash-50 font-ui font-semibold text-ash-500 transition-all duration-200 hover:border-gold-400 hover:bg-white hover:text-ash-800 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-amber-400/30 ${
        compact ? 'px-2.5 py-1.5 text-xs' : small ? 'px-3 py-1.5 text-xs' : 'px-4 py-2 text-[13px]'
      }`}
    >
      {typeof icon === 'string' ? (
        <span aria-hidden="true" className={`material-symbols-outlined ${small ? 'text-[15px]' : 'text-[16px]'}`}>
          {icon}
        </span>
      ) : (
        icon
      )}
      {/* compact (a phone's query box): icon and lock only; the label is still read out. */}
      <span className={compact ? 'sr-only' : ''}>{label}</span>
      <span
        aria-hidden="true"
        className="ml-0.5 inline-flex items-center gap-0.5 rounded-full bg-amber-400/20 px-1.5 py-0.5 text-[9.5px] font-bold uppercase tracking-wider text-gold-700 transition-colors group-hover:bg-amber-400/30"
      >
        <span className="material-symbols-outlined text-[11px]">lock</span>
        {!compact && 'Pro'}
      </span>
    </button>
  );
};

const PERKS = [
  'Every relevant judgment, ten at a time',
  'Analyse and summarise each case',
  'Filter and compare judgments',
  'Download the PDF and copy the text',
];

const PlanOption = ({ plan, highlight }) => (
  <div
    className={`flex flex-1 flex-col rounded-2xl border p-4 ${
      highlight ? 'border-brand-300 bg-brand-50/60' : 'border-ash-200 bg-white'
    }`}
  >
    <div className="flex items-baseline justify-between gap-2">
      <span className="font-display text-[14px] font-bold text-ash-900">{plan.name}</span>
      <span className="font-display text-[15px] font-bold text-ash-900">
        ${plan.price}
        <span className="font-prose text-[11px] font-normal text-ash-500"> / month</span>
      </span>
    </div>
    <span className="mt-1 font-ui text-[12px] font-semibold text-brand-700">
      {plan.dailyLimit} searches a day
    </span>
  </div>
);

/**
 * Why a tool is locked and what unlocks it. Closes on Escape, on the backdrop
 * and on "Not now"; the primary action is last, where the eye ends up.
 */
export const UpgradeDialog = ({ feature, message, onClose }) => {
  const primary = useRef(null);

  useEffect(() => {
    primary.current?.focus();
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const label = FEATURE_LABELS[feature] || 'This tool';
  const free = PLANS.free;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-ash-900/45 backdrop-blur-sm sm:items-center sm:p-6"
      onClick={onClose}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="upgrade-title"
        aria-describedby="upgrade-body"
        className="w-full overflow-hidden rounded-t-3xl bg-white shadow-card-lg sm:max-w-lg sm:rounded-3xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-6 pb-2 pt-6">
          <span
            aria-hidden="true"
            className="flex h-11 w-11 items-center justify-center rounded-2xl bg-amber-400/20 text-gold-700"
          >
            <span className="material-symbols-outlined text-[22px]">lock</span>
          </span>
          <h2 id="upgrade-title" className="mt-4 font-display text-lg font-bold text-ash-900">
            {label} is a paid feature
          </h2>
          <p id="upgrade-body" className="mt-1.5 font-prose text-[13.5px] leading-relaxed text-ash-600">
            {message ||
              `The Free plan gives you ${free.dailyLimit} searches a day and summaries of up to ${free.maxResults} relevant judgments. Upgrade to unlock every research tool.`}
          </p>
        </div>

        <div className="px-6 py-4">
          <div className="flex flex-col gap-2.5 sm:flex-row">
            <PlanOption plan={PLANS.standard} highlight />
            <PlanOption plan={PLANS.premium} />
          </div>
          <ul className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
            {PERKS.map((perk) => (
              <li key={perk} className="flex items-start gap-2 font-prose text-[12.5px] leading-snug text-ash-700">
                <span aria-hidden="true" className="material-symbols-outlined mt-px text-[15px] text-mint-700">
                  check_circle
                </span>
                {perk}
              </li>
            ))}
          </ul>
        </div>

        <div className="flex flex-col-reverse gap-2.5 border-t border-ash-200 bg-ash-50/60 px-6 py-4 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onClose}
            className="inline-flex min-h-[40px] items-center justify-center rounded-full border border-ash-300 bg-white px-5 font-ui text-[13px] font-semibold text-ash-700 transition-colors hover:border-ash-400 hover:text-ash-900"
          >
            Not now
          </button>
          <Link
            ref={primary}
            to="/pricing"
            className="grad-btn inline-flex min-h-[40px] items-center justify-center gap-1.5 rounded-full px-5 font-ui text-[13px] font-bold text-white shadow-glow transition-all hover:-translate-y-0.5 hover:shadow-glow-lg focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand-500/30"
          >
            See plans
            <span aria-hidden="true" className="material-symbols-outlined text-[16px]">arrow_forward</span>
          </Link>
        </div>
      </div>
    </div>
  );
};

/** One line under a Free result: what the plan shows, and the way up. */
export const FreePlanNote = () => (
  <div className="mt-6 flex flex-wrap items-center gap-3 rounded-2xl border border-amber-400/40 bg-amber-400/10 px-4 py-3">
    <span aria-hidden="true" className="material-symbols-outlined text-[18px] text-gold-700">
      workspace_premium
    </span>
    <p className="min-w-0 flex-1 font-prose text-[13px] leading-relaxed text-ash-700">
      <strong className="font-semibold text-ash-900">Free plan:</strong> summaries of the top{' '}
      {PLANS.free.maxResults} relevant judgments. Upgrade to analyse, compare, filter, download and
      see every relevant judgment.
    </p>
    <Link
      to="/pricing"
      className="inline-flex items-center gap-1 rounded-full bg-white px-3.5 py-1.5 font-ui text-[12px] font-bold text-brand-700 shadow-xs ring-1 ring-ash-200 transition-all hover:ring-brand-300"
    >
      See plans
      <span aria-hidden="true" className="material-symbols-outlined text-[15px]">arrow_forward</span>
    </Link>
  </div>
);
