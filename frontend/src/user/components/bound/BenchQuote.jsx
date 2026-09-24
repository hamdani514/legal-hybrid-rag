import Reveal from '../Reveal';
import MediaFrame from './MediaFrame';

/**
 * A single passage, given the room a single passage deserves.
 *
 * This is the one place on the site where the Court speaks in its own words
 * at length rather than in a facsimile widget. The quotation and its appeal
 * number are the same ones the hero previews, so the reader who scrolled
 * past that panel meets the finding again with the weight behind it.
 *
 * The photograph is 940×475 — the widest source in the library — which is
 * why this band is the one that runs edge to edge.
 */

/** The six divisions, cycled beneath the quote. Duplicated once so the
 *  marquee wraps seamlessly; the copy is hidden from assistive tech. */
const DIVISIONS = [
  'Header & Coram',
  'Facts',
  'Arguments',
  'Legal Issues',
  'Analysis & Ratio',
  'Final Order',
];

const BenchQuote = () => {
  return (
    <section aria-labelledby="bench-quote-title" className="relative w-full">
      <MediaFrame
        name="bench"
        wash="edge"
        grain
        drift
        ratio="auto"
        className="flex min-h-[34rem] w-full items-center"
      >
        <div className="relative z-[1] mx-auto w-full max-w-[1200px] px-5 py-20 sm:px-8 sm:py-24">
          <div className="max-w-[46rem]">
            <Reveal variant="fade">
              <span className="inline-flex items-center gap-2 rounded-full border border-white/25 bg-white/12 px-4 py-1.5 font-ui text-[12.5px] font-semibold text-white backdrop-blur-sm">
                <span aria-hidden="true" className="material-symbols-outlined text-[15px]">
                  gavel
                </span>
                From the record
              </span>
            </Reveal>

            <span
              aria-hidden="true"
              className="material-symbols-outlined mt-8 block text-[44px] leading-none text-brand-200/80"
            >
              format_quote
            </span>

            <Reveal as="figure" delay={90} className="mt-2">
              <blockquote>
                <p
                  id="bench-quote-title"
                  className="font-display text-[clamp(1.5rem,3.4vw,2.375rem)] font-semibold leading-[1.3] tracking-[-0.022em] text-balance text-white"
                >
                  The dispute concerned wrong entries in the revenue record, which{' '}
                  <span className="text-brand-100">
                    in no way can be termed as a matter relating to dower
                  </span>
                  .
                </p>
              </blockquote>

              <figcaption className="mt-7 flex flex-wrap items-center gap-x-4 gap-y-3">
                <cite className="font-display text-[14px] font-bold not-italic text-white">
                  Civil Appeal No. 23-P of 2017
                </cite>
                <span aria-hidden="true" className="h-4 w-px bg-white/25" />
                <span className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-3 py-1 font-ui text-[11.5px] font-bold text-white backdrop-blur-sm">
                  <span aria-hidden="true" className="material-symbols-outlined text-[14px]">
                    check_circle
                  </span>
                  Appeal dismissed
                </span>
                <span className="inline-flex items-center gap-1.5 rounded-full border border-white/25 px-3 py-1 font-ui text-[11.5px] font-medium text-white/80">
                  Analysis &amp; Ratio
                </span>
              </figcaption>
            </Reveal>

            <Reveal
              as="p"
              variant="fade"
              delay={200}
              className="mt-8 max-w-[38rem] font-prose text-[15px] leading-[1.78] text-white/75"
            >
              Retrieved from the ratio, not from a headnote — which is why the division it came
              from can be named beside it.
            </Reveal>
          </div>
        </div>
      </MediaFrame>

      {/* The divisions, cycling. A quiet reminder of the structure that made
          the passage above reachable in the first place. */}
      <div className="marquee-mask relative overflow-hidden border-y border-ash-200 bg-white py-5">
        <ul className="marquee-track flex items-center gap-10 sm:gap-14">
          {[...DIVISIONS, ...DIVISIONS].map((label, index) => (
            <li
              key={`${label}-${index}`}
              className="flex shrink-0 items-center gap-3"
              aria-hidden={index >= DIVISIONS.length ? 'true' : undefined}
            >
              <span
                aria-hidden="true"
                className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-50 text-brand-600"
              >
                <span className="material-symbols-outlined text-[15px]">check</span>
              </span>
              <span className="whitespace-nowrap font-display text-[14px] font-semibold tracking-[-0.01em] text-ash-700">
                {label}
              </span>
              <span aria-hidden="true" className="h-1 w-1 rounded-full bg-ash-300" />
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
};

export default BenchQuote;
