import { useEffect, useRef, useState } from 'react';
import Reveal from '../Reveal';
import SectionOpener from './SectionOpener';

const DURATION = 1500;

const skipCount = () =>
  typeof window === 'undefined' ||
  typeof IntersectionObserver === 'undefined' ||
  (typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches);

/**
 * Counts to `value` the first time it enters view. The final figure is in the
 * accessible name from the first paint, so a screen reader never hears a
 * half-counted number, and the animation is skipped entirely under reduced
 * motion.
 */
const Tally = ({ value, decimals = 0, suffix = '', className = '' }) => {
  const ref = useRef(null);
  const [shown, setShown] = useState(() => (skipCount() ? value : 0));

  useEffect(() => {
    const node = ref.current;
    if (!node || skipCount()) return undefined;

    let frame = 0;
    let start = 0;

    const step = (now) => {
      if (!start) start = now;
      const p = Math.min((now - start) / DURATION, 1);
      setShown(value * (1 - Math.pow(1 - p, 3)));
      if (p < 1) frame = requestAnimationFrame(step);
    };

    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            io.unobserve(entry.target);
            frame = requestAnimationFrame(step);
          }
        });
      },
      { threshold: 0.45 }
    );

    io.observe(node);
    return () => {
      io.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [value]);

  const fmt = (n) =>
    n.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

  return (
    <span ref={ref} className={className}>
      <span aria-hidden="true">
        {fmt(shown)}
        {suffix}
      </span>
      <span className="sr-only">
        {fmt(value)}
        {suffix}
      </span>
    </span>
  );
};

/**
 * What is in the archive right now, counted live by GET /api/stats.
 *
 * These replace accuracy percentages: a count of the archive can be checked by
 * anyone, while an accuracy figure needs a frozen, reproducible test behind it
 * before it is published. The numbers grow as judgments are ingested.
 */
const CARDS = [
  {
    key: 'judgments',
    tag: 'Archive',
    icon: 'gavel',
    iconBg: 'bg-sky-50 text-sky-600 border-sky-100',
    barColor: 'from-sky-500 to-brand-600',
    label: 'Judgments in the archive',
    basis: 'Reported judgments of the Supreme Court of Pakistan, every one searchable now',
  },
  {
    key: 'scanned_judgments',
    tag: 'Scanned PDFs',
    icon: 'document_scanner',
    iconBg: 'bg-emerald-50 text-emerald-600 border-emerald-100',
    barColor: 'from-emerald-500 to-teal-600',
    label: 'Scanned judgments read by OCR',
    basis: 'Paper judgments straightened, read page by page and indexed like typed ones',
  },
  {
    key: 'sections',
    tag: 'Structure',
    icon: 'account_tree',
    iconBg: 'bg-indigo-50 text-indigo-600 border-indigo-100',
    barColor: 'from-indigo-500 to-purple-600',
    label: 'Judgment sections marked',
    basis: 'Coram, facts, arguments, issues, ratio and final order, in every judgment',
  },
  {
    key: 'passages',
    tag: 'Search Index',
    icon: 'manage_search',
    iconBg: 'bg-brand-50 text-brand-600 border-brand-100',
    barColor: 'from-brand-500 to-blue-600',
    label: 'Passages indexed for search',
    basis: 'Each one searchable by its meaning and by its exact words',
  },
];

const COUNT_CLASS =
  'font-display text-[clamp(2.4rem,4.8vw,3.25rem)] font-extrabold leading-none tracking-[-0.035em] tabular-nums';

const formatUpdated = (iso) => {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString('en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const MetricsBand = () => {
  const [stats, setStats] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch('/api/stats');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!cancelled) setStats(data);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const years =
    stats?.first_year && stats?.last_year ? `${stats.first_year} to ${stats.last_year}` : '';
  const updated = stats?.updated_at ? formatUpdated(stats.updated_at) : '';

  return (
    <section aria-labelledby="metrics-title" className="w-full bg-white px-5 py-12 sm:px-8 md:py-16">
      <div className="mx-auto max-w-[1200px]">
        {/* Section Header */}
        <SectionOpener
          eyebrow="The Archive Today"
          icon="inventory_2"
          title={<span id="metrics-title">What the archive</span>}
          accent="holds right now"
          lede="Counted live from the database each time this page loads, so the figures grow as new judgments are added."
          className="mx-auto"
        />

        {/* 4 live count cards */}
        <dl className="mt-10 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4 sm:mt-12">
          {CARDS.map(({ key, tag, icon, iconBg, barColor, label, basis }, index) => {
            const value = stats?.[key];
            return (
              <Reveal
                key={key}
                variant="scale"
                delay={index * 100}
                className="group relative flex flex-col justify-between overflow-hidden rounded-3xl border border-ash-200 bg-white p-7 shadow-soft transition-all duration-300 hover:-translate-y-1 border-trace hover:border-brand-100 hover:shadow-card-lg"
              >
                {/* Top Accent Gradient Bar on Hover */}
                <span
                  aria-hidden="true"
                  className={`absolute inset-x-0 top-0 h-1 bg-gradient-to-r ${barColor} opacity-0 transition-opacity duration-300 group-hover:opacity-100`}
                />

                <div>
                  {/* Header row with icon and tag */}
                  <div className="flex items-center justify-between gap-2">
                    <span
                      className={`flex h-10 w-10 items-center justify-center rounded-2xl border ${iconBg} shadow-xs`}
                    >
                      <span className="material-symbols-outlined text-[20px]" aria-hidden="true">
                        {icon}
                      </span>
                    </span>

                    <span className="rounded-full border border-ash-200 bg-ash-50 px-3 py-1 font-ui text-[11.5px] font-semibold tracking-wide text-ash-600">
                      {tag}
                    </span>
                  </div>

                  {/* The live count; a placeholder until it arrives, a dash if it cannot */}
                  <div className="mt-6 flex items-baseline">
                    {typeof value === 'number' ? (
                      <Tally
                        value={value}
                        className={`${COUNT_CLASS} text-ash-900 transition-colors duration-300 group-hover:text-brand-600`}
                      />
                    ) : failed ? (
                      <span className={`${COUNT_CLASS} text-ash-300`}>—</span>
                    ) : (
                      <span aria-hidden="true" className="h-[2.6rem] w-32 animate-pulse rounded-xl bg-ash-100" />
                    )}
                  </div>

                  {/* Label */}
                  <dt className="mt-4 font-display text-[15px] font-bold leading-snug text-ash-900">
                    {label}
                  </dt>
                </div>

                {/* Basis Footnote inside Card */}
                <dd className="mt-6 border-t border-ash-100 pt-4 font-prose text-[13px] leading-[1.65] text-ash-500">
                  {basis}
                </dd>
              </Reveal>
            );
          })}
        </dl>

        {/* How the figures are produced */}
        <Reveal delay={380} className="mt-10">
          <div className="flex flex-col items-start gap-4 rounded-3xl border border-ash-200 bg-ash-50/70 p-6 sm:flex-row sm:items-center sm:gap-6 sm:p-7">
            <span
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-ash-200 bg-white text-brand-600 shadow-sm"
              aria-hidden="true"
            >
              <span className="material-symbols-outlined text-[22px]">fact_check</span>
            </span>

            <div className="flex-1">
              <h4 className="font-display text-[14.5px] font-bold text-ash-900">
                Counted, not estimated
              </h4>
              <p className="mt-1 font-prose text-[13px] leading-[1.7] text-ash-600">
                Every figure above is a live count of what is in the archive today
                {years ? `, covering decisions from ${years}` : ''}. Search accuracy will be
                published here only once the evaluation set is frozen and run, with its method
                stated.{updated ? ` Last counted ${updated}.` : ''}
              </p>
            </div>

            <div className="flex shrink-0 items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3.5 py-1.5 font-ui text-[12px] font-bold text-emerald-700">
              <span className="material-symbols-outlined text-[16px]">sensors</span>
              Live count
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
};

export default MetricsBand;
