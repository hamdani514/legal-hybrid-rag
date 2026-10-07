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
 * Figures from the project's own evaluation. Every number here is measured,
 * and each carries the basis it was measured on — an unqualified accuracy
 * figure is the kind of claim that does not survive a question.
 */
const METRICS = [
  {
    value: 94.1,
    decimals: 1,
    suffix: '%',
    tag: 'Top-1 Accuracy',
    icon: 'radar',
    iconBg: 'bg-sky-50 text-sky-600 border-sky-100',
    barColor: 'from-sky-500 to-brand-600',
    label: 'Correct judgment ranked first',
    basis: 'Over a 17-query labelled ground-truth benchmark set',
  },
  {
    value: 100,
    suffix: '%',
    tag: 'Verdict Fidelity',
    icon: 'verified',
    iconBg: 'bg-emerald-50 text-emerald-600 border-emerald-100',
    barColor: 'from-emerald-500 to-teal-600',
    label: 'Dispositions reported correctly',
    basis: 'Allowed or dismissed accurately across every judgment tested',
  },
  {
    value: 6,
    tag: 'Structural Parsing',
    icon: 'account_tree',
    iconBg: 'bg-indigo-50 text-indigo-600 border-indigo-100',
    barColor: 'from-indigo-500 to-purple-600',
    label: 'Divisions marked per judgment',
    basis: 'Coram, facts, arguments, issues, ratio, and final order',
  },
  {
    value: 2,
    tag: 'Two-Stage Pass',
    icon: 'layers',
    iconBg: 'bg-brand-50 text-brand-600 border-brand-100',
    barColor: 'from-brand-500 to-blue-600',
    label: 'Retrieval passes per query',
    basis: 'Judgment-level reranking followed by passage-level extraction',
  },
];

const MetricsBand = () => {
  return (
    <section aria-labelledby="metrics-title" className="w-full bg-white px-5 py-20 sm:px-8 md:py-28">
      <div className="mx-auto max-w-[1200px]">
        {/* Section Header */}
        <SectionOpener
          eyebrow="Evaluation & Benchmarks"
          icon="insights"
          title={<span id="metrics-title">Measured, with the</span>}
          accent="basis stated"
          lede="Figures describe the current benchmark corpus and verified query set. We test pipeline behaviour rigorously rather than making blanket claims."
          className="mx-auto"
        />

        {/* 4 Metric Cards */}
        <dl className="mt-12 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4 sm:mt-16">
          {METRICS.map(({ value, decimals, suffix, tag, icon, iconBg, barColor, label, basis }, index) => (
            <Reveal
              key={label}
              variant="scale"
              delay={index * 100}
              className="group relative flex flex-col justify-between overflow-hidden rounded-3xl border border-ash-200 bg-white p-7 shadow-soft transition-all duration-300 hover:-translate-y-1 hover:border-brand-200 hover:shadow-card-lg"
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

                {/* Big Tally Metric */}
                <div className="mt-6 flex items-baseline">
                  <Tally
                    value={value}
                    decimals={decimals}
                    suffix={suffix}
                    className="font-display text-[clamp(2.4rem,4.8vw,3.25rem)] font-extrabold leading-none tracking-[-0.035em] tabular-nums text-ash-900 group-hover:text-brand-600 transition-colors duration-300"
                  />
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
          ))}
        </dl>

        {/* Methodology Disclosure Note */}
        <Reveal delay={380} className="mt-10">
          <div className="flex flex-col items-start gap-4 rounded-3xl border border-ash-200 bg-ash-50/70 p-6 sm:flex-row sm:items-center sm:gap-6 sm:p-7">
            <span
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-ash-200 bg-white text-brand-600 shadow-sm"
              aria-hidden="true"
            >
              <span className="material-symbols-outlined text-[22px]">science</span>
            </span>

            <div className="flex-1">
              <h4 className="font-display text-[14.5px] font-bold text-ash-900">
                Independent Verification Protocol
              </h4>
              <p className="mt-1 font-prose text-[13px] leading-[1.7] text-ash-600">
                Figures describe the current corpus and labelled test set. They validate the pipeline&rsquo;s retrieval precision rather than establishing blanket claims, and are re-benchmarked after any change to ingestion chunking or the embedding model.
              </p>
            </div>

            <div className="flex shrink-0 items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3.5 py-1.5 font-ui text-[12px] font-bold text-emerald-700">
              <span className="material-symbols-outlined text-[16px]">verified</span>
              Reproducible
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
};

export default MetricsBand;
