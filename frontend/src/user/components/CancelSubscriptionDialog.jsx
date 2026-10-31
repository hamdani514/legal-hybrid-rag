import { useEffect, useRef } from 'react';
import { PLANS } from '../lib/plan';

/**
 * Confirms cancelling a paid subscription — the app's own dialog, not the
 * browser's confirm box.
 *
 * Cancelling is the destructive choice, so the safe one ("Keep …") has the
 * focus when the dialog opens: Enter on autopilot keeps the plan. The dialog
 * says plainly what is kept, until when, and what Free then means. Escape and
 * the backdrop close it, except while the request is running.
 */
const CancelSubscriptionDialog = ({ planName, dailyLimit, endsLabel, busy, onConfirm, onClose }) => {
  const keep = useRef(null);
  const free = PLANS.free;

  useEffect(() => {
    keep.current?.focus();
  }, []);

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && !busy && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [busy, onClose]);

  const after = [
    `${free.dailyLimit} searches a day instead of ${dailyLimit}`,
    `Summaries of the top ${free.maxResults} judgments only`,
    'Analysis, filters, comparison, downloads and copying locked',
    'Your payment card removed automatically',
  ];

  return (
    <div
      className="fixed inset-0 z-[70] flex items-end justify-center bg-ash-900/45 backdrop-blur-sm sm:items-center sm:p-6"
      onClick={() => !busy && onClose()}
      role="presentation"
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="cancel-sub-title"
        aria-describedby="cancel-sub-body"
        className="w-full overflow-hidden rounded-t-3xl bg-white text-left shadow-card-lg sm:max-w-md sm:rounded-3xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-6 pb-2 pt-6">
          <span
            aria-hidden="true"
            className="flex h-11 w-11 items-center justify-center rounded-2xl bg-rose-50 text-rose-600"
          >
            <span className="material-symbols-outlined text-[22px]">event_busy</span>
          </span>
          <h2 id="cancel-sub-title" className="mt-4 font-display text-lg font-bold text-ash-900">
            Cancel your {planName} subscription?
          </h2>
          <p id="cancel-sub-body" className="mt-1.5 font-prose text-[13.5px] leading-relaxed text-ash-600">
            You keep full {planName} access — {dailyLimit} searches a day and every research tool — until{' '}
            <strong className="font-semibold text-ash-900">{endsLabel}</strong>. You will not be charged again.
          </p>
        </div>

        <div className="mx-6 my-4 rounded-2xl border border-ash-200 bg-ash-50/70 px-4 py-3.5">
          <p className="font-ui text-[10.5px] font-bold uppercase tracking-[0.1em] text-ash-500">
            After {endsLabel}, on the Free plan
          </p>
          <ul className="mt-2.5 flex flex-col gap-2">
            {after.map((item) => (
              <li key={item} className="flex items-start gap-2 font-prose text-[13px] leading-snug text-ash-700">
                <span aria-hidden="true" className="material-symbols-outlined mt-px text-[15px] text-ash-400">
                  remove_circle_outline
                </span>
                {item}
              </li>
            ))}
          </ul>
        </div>

        <p className="px-6 pb-5 font-prose text-[12.5px] text-ash-500">
          Changed your mind later? You can reactivate before {endsLabel}.
        </p>

        <div className="flex flex-col-reverse gap-2.5 border-t border-ash-200 bg-ash-50/60 px-6 py-4 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className="inline-flex min-h-[40px] items-center justify-center gap-1.5 rounded-full border border-rose-300 bg-white px-5 font-ui text-[13px] font-bold text-rose-700 transition-colors hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy && (
              <span aria-hidden="true" className="material-symbols-outlined animate-spin text-[16px]">
                progress_activity
              </span>
            )}
            {busy ? 'Cancelling…' : 'Cancel subscription'}
          </button>
          <button
            ref={keep}
            type="button"
            onClick={onClose}
            disabled={busy}
            className="grad-btn inline-flex min-h-[40px] items-center justify-center rounded-full px-5 font-ui text-[13px] font-bold text-white shadow-glow transition-all hover:-translate-y-0.5 hover:shadow-glow-lg focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand-500/30 disabled:opacity-60"
          >
            Keep {planName}
          </button>
        </div>
      </div>
    </div>
  );
};

export default CancelSubscriptionDialog;
