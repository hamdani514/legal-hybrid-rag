import { useEffect, useRef, useState } from 'react';
import Reveal from '../Reveal';

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
 * Figures from the project's own evaluation. Every number here is measured,
 * and each carries the basis it was measured on — an unqualified accuracy
 * figure is the kind of claim that does not survive a question.
 */
const METRICS = [
  {
    value: 94.1,
    decimals: 1,
    suffix: '%',
    label: 'Correct judgment ranked first',
    basis: 'Over a 17-query labelled set',
  },
  {
    value: 100,
    suffix: '%',
    label: 'Dispositions reported correctly',
    basis: 'Allowed or dismissed, every judgment tested',
  },
  {
    value: 6,
    label: 'Divisions marked per judgment',
    basis: 'Coram, facts, arguments, issues, ratio, order',
  },
  {
    value: 2,
    label: 'Retrieval passes per query',
    basis: 'Judgment level, then passage level',
  },
];

const MetricsBand = () => {
  return (
    <section aria-labelledby="metrics-title" className="w-full px-5 py-20 sm:px-8 md:py-28">
      <Reveal className="mx-auto max-w-[1200px]">
        <div className="grad-brand relative overflow-hidden rounded-4xl px-6 py-14 sm:px-11 sm:py-16">
          <span
            aria-hidden="true"
            className="float-y-slow pointer-events-none absolute -right-20 -top-20 h-72 w-72 rounded-full bg-white/10 blur-3xl"
          />

          <div className="relative">
            <span className="inline-flex items-center gap-2 rounded-full border border-white/25 bg-white/12 px-4 py-1.5 font-ui text-[12.5px] font-semibold text-white backdrop-blur-sm">
              <span className="material-symbols-outlined text-[15px]" aria-hidden="true">
                insights
              </span>
              Evaluation
            </span>

            <h2
              id="metrics-title"
              className="mt-6 max-w-[32rem] font-display text-[clamp(1.75rem,4vw,2.5rem)] font-bold leading-[1.12] tracking-[-0.03em] text-white"
            >
              Measured, with the basis stated
            </h2>

            <dl className="mt-11 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {METRICS.map(({ value, decimals, suffix, label, basis }, index) => (
                <Reveal
                  key={label}
                  delay={index * 100}
                  className="rounded-3xl border border-white/15 bg-white/10 p-6 backdrop-blur-sm transition-colors duration-300 hover:bg-white/15"
                >
                  <Tally
                    value={value}
                    decimals={decimals}
                    suffix={suffix}
                    className="font-display text-[clamp(2.25rem,4.6vw,2.875rem)] font-bold leading-none tracking-[-0.035em] tabular-nums text-white"
                  />
                  <dt className="mt-4 font-display text-[13.5px] font-bold leading-5 text-brand-100">
                    {label}
                  </dt>
                  <dd className="mt-1.5 font-prose text-[12.5px] leading-5 text-white/70">
                    {basis}
                  </dd>
                </Reveal>
              ))}
            </dl>

            <p className="mt-8 max-w-[44rem] font-prose text-[12.5px] leading-[1.65] text-white/65">
              Figures describe the current corpus and query set. They validate the
              pipeline&rsquo;s behaviour rather than establishing accuracy at scale, and are
              re-measured after any change to ingestion or the embedding model.
            </p>
          </div>
        </div>
      </Reveal>
    </section>
  );
};

export default MetricsBand;
