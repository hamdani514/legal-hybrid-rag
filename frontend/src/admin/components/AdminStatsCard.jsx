/**
 * A summary tile for the console. These sit above the detail tables, so the
 * figure carries the weight and the label stays quiet.
 *
 * `tone` colours the icon tile semantically — separate from the brand accent,
 * so "failed" reads as a problem at a glance rather than as another statistic.
 */
const TONES = {
  brand: 'bg-brand-50 text-brand-600',
  good: 'bg-mint-400/15 text-mint-700',
  warn: 'bg-amber-400/15 text-amber-500',
  bad: 'bg-red-50 text-red-600',
  neutral: 'bg-ash-100 text-ash-500',
};

const AdminStatsCard = ({ label, value, subtext, icon, loading, tone = 'brand' }) => {
  return (
    <div className="lift-card rounded-3xl border border-ash-200 bg-white p-6 shadow-soft transition-all hover:border-brand-200 hover:shadow-card">
      <div className="flex items-start justify-between gap-4">
        <span className="font-ui text-[11.5px] font-semibold uppercase tracking-[0.1em] text-ash-500">
          {label}
        </span>
        {icon && (
          <span
            aria-hidden="true"
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl ${
              TONES[tone] ?? TONES.brand
            }`}
          >
            <span className="material-symbols-outlined text-[20px]">{icon}</span>
          </span>
        )}
      </div>

      <p className="mt-5 font-display text-[2.5rem] font-bold leading-none tracking-[-0.035em] tabular-nums text-ash-900">
        {loading ? (
          // A pulsing bar rather than an ellipsis, so the tile does not
          // change height when the figure arrives.
          <span
            className="inline-block h-9 w-20 animate-pulse rounded-lg bg-ash-100 align-bottom"
            role="status"
            aria-label={`Loading ${label}`}
          />
        ) : (
          value
        )}
      </p>

      {subtext && (
        <p className="mt-3 font-prose text-[13px] leading-5 text-ash-500">{subtext}</p>
      )}
    </div>
  );
};

export default AdminStatsCard;
