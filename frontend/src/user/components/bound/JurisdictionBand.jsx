import { Link } from 'react-router-dom';
import Reveal from '../Reveal';
import MediaFrame from './MediaFrame';

/**
 * The full-bleed band that names the jurisdiction.
 *
 * It sits directly under the assurance strip because the claim made above it
 * — structured, cited, honest about its limits — only means something once
 * the reader knows how narrow the ground is. One court, its reported
 * judgments, and nothing borrowed from anywhere else.
 *
 * The photograph is capped at 34rem and run under a brand wash rather than
 * stretched to the viewport: the source file is 735px wide, and past that it
 * reads soft. Under the wash it reads as a ground, which is the job.
 */
const FIGURES = [
  { value: 'Supreme Court', unit: 'of Pakistan', note: 'The only bench in the index' },
  { value: 'Six', unit: 'divisions', note: 'Marked on every judgment' },
  { value: 'Two', unit: 'passes', note: 'Judgment, then passage' },
  { value: '384', unit: 'dimensions', note: 'Per embedded passage' },
];

const JurisdictionBand = () => {
  return (
    <section aria-labelledby="jurisdiction-title" className="relative w-full">
      <MediaFrame
        name="court"
        wash="brand"
        grain
        drift
        ratio="auto"
        className="flex min-h-[38rem] w-full items-center lg:min-h-[34rem]"
      >
        {/* Ambient blooms, so the band shares the vocabulary of the gradient
            panels either side of it rather than looking like a stock photo. */}
        <span
          aria-hidden="true"
          className="float-y-slow pointer-events-none absolute -right-24 -top-24 h-80 w-80 rounded-full bg-cyan-300/20 blur-3xl"
        />
        <span
          aria-hidden="true"
          className="float-y pointer-events-none absolute -bottom-28 -left-20 h-72 w-72 rounded-full bg-violet-600/25 blur-3xl"
        />

        <div className="relative z-[1] mx-auto flex w-full max-w-[1200px] flex-col justify-center px-5 py-20 sm:px-8 sm:py-24">
          <Reveal variant="fade">
            <span className="inline-flex items-center gap-2 rounded-full border border-white/25 bg-white/12 px-4 py-1.5 font-ui text-[12.5px] font-semibold text-white backdrop-blur-sm">
              <span aria-hidden="true" className="material-symbols-outlined text-[15px]">
                account_balance
              </span>
              Islamabad · Constitution Avenue
            </span>
          </Reveal>

          <Reveal
            as="h2"
            delay={90}
            id="jurisdiction-title"
            className="mt-7 max-w-[24ch] font-display text-[clamp(2rem,5vw,3.25rem)] font-bold leading-[1.08] tracking-[-0.032em] text-balance text-white"
          >
            One jurisdiction, <span className="text-brand-100">read closely</span>
          </Reveal>

          <Reveal
            as="p"
            delay={160}
            className="mt-6 max-w-[40rem] font-prose text-[1.0625rem] leading-[1.8] text-white/85"
          >
            Everything indexed here was handed down by the Supreme Court of Pakistan and reported.
            Nothing is inferred from a summary, a headnote or a secondary source. A narrow archive
            read properly is worth more than a wide one skimmed.
          </Reveal>

          {/* Figures, on glass so the photograph still shows beneath. */}
          <dl className="mt-12 grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
            {FIGURES.map(({ value, unit, note }, index) => (
              <Reveal
                key={value + unit}
                delay={220 + index * 80}
                className="rounded-3xl border border-white/20 bg-white/10 p-5 backdrop-blur-md transition-colors duration-300 hover:bg-white/[0.17] sm:p-6"
              >
                <dt className="font-display text-[clamp(1.25rem,2.6vw,1.75rem)] font-bold leading-[1.15] tracking-[-0.03em] text-white">
                  {value}
                  <span className="block font-ui text-[12.5px] font-semibold uppercase tracking-[0.1em] text-brand-100">
                    {unit}
                  </span>
                </dt>
                <dd className="mt-3 font-prose text-[12.5px] leading-5 text-white/70">{note}</dd>
              </Reveal>
            ))}
          </dl>

          <Reveal delay={520} variant="fade" className="mt-10">
            <Link
              to="/about"
              className="group inline-flex items-center gap-2.5 rounded-full border border-white/35 bg-white/10 px-7 py-3.5 font-ui text-[14.5px] font-semibold text-white backdrop-blur-sm transition-all duration-300 hover:border-white/60 hover:bg-white/20"
            >
              What gets indexed, and what does not
              <span
                aria-hidden="true"
                className="material-symbols-outlined text-[18px] transition-transform duration-300 group-hover:translate-x-1"
              >
                arrow_forward
              </span>
            </Link>
          </Reveal>
        </div>
      </MediaFrame>
    </section>
  );
};

export default JurisdictionBand;
