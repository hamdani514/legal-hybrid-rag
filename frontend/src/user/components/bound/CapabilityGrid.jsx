import Reveal from '../Reveal';
import SectionOpener from './SectionOpener';

/**
 * What the workspace does. The lead capability gets a wide card with a live
 * facsimile; the rest are equal panels. Weight is spent on the first item
 * only, so the eye has somewhere to land.
 */
const SUPPORTING = [
  {
    icon: 'compare_arrows',
    title: 'Compare authorities',
    body: 'Set two lines of authority side by side and see where they diverge on the same question.',
  },
  {
    icon: 'segment',
    title: 'Jump to any division',
    body: 'Go straight to the ratio or the order without scrolling a forty-page volume.',
  },
  {
    icon: 'download',
    title: 'Export with the citation',
    body: 'Take a passage out as clean text with its appeal number and disposition attached.',
  },
  {
    icon: 'history',
    title: 'Keep a research trail',
    body: 'Every query and the authorities it returned are saved, so you can pick the thread back up.',
  },
];

const CapabilityGrid = () => {
  return (
    <section
      aria-labelledby="capability-title"
      className="ground-tint w-full border-y border-ash-200 px-5 py-20 sm:px-8 md:py-28"
    >
      <div className="mx-auto max-w-[1200px]">
        <SectionOpener
          eyebrow="In the workspace"
          icon="workspaces"
          title={<span id="capability-title">Built for the way research</span>}
          accent="actually runs"
          lede="Not a search box bolted onto a PDF library. The tools follow the shape of the work — question, authority, passage, brief."
          className="mx-auto"
        />

        <div className="mt-14 grid grid-cols-1 gap-5 md:mt-20 lg:grid-cols-[1.2fr_1fr]">
          {/* ── Lead capability ─────────────────────────────────────── */}
          <Reveal className="lift-card flex flex-col justify-between rounded-4xl border border-ash-200 bg-white p-8 shadow-card hover:border-brand-200 hover:shadow-card-lg sm:p-10">
            <div>
              <span
                aria-hidden="true"
                className="grad-brand flex h-14 w-14 items-center justify-center rounded-2xl text-white shadow-glow"
              >
                <span className="material-symbols-outlined text-[24px]">travel_explore</span>
              </span>

              <h3 className="mt-7 font-display text-[clamp(1.625rem,3vw,2.125rem)] font-bold leading-[1.14] tracking-[-0.025em] text-ash-900">
                Ask a legal question, not a keyword
              </h3>

              <p className="mt-4 max-w-[34rem] font-prose text-[15.5px] leading-[1.74] text-ash-600">
                Phrase it the way you would to a colleague. The archive matches meaning, so a
                question about Family Court jurisdiction reaches the judgment that decided it —
                whether or not it shares your words.
              </p>
            </div>

            {/* Facsimile */}
            <div
              className="mt-8 overflow-hidden rounded-3xl border border-ash-200 bg-ash-50"
              aria-hidden="true"
            >
              <p className="border-b border-ash-200 bg-white px-5 py-4 font-prose text-[14px] italic leading-6 text-ash-700">
                “Is a claim relating to dower within the jurisdiction of a Family Court?”
              </p>
              <ul className="divide-y divide-ash-200">
                {[
                  ['Civil Appeal No. 23-P of 2017', '0.69', true],
                  ['Civil Appeal No. 43-Q of 2018', '0.59', false],
                  ['Civil Appeal No. 42-K of 2016', '0.58', false],
                ].map(([ref, score, top]) => (
                  <li key={ref} className="flex items-center justify-between gap-4 px-5 py-3">
                    <span className="truncate font-display text-[13px] font-semibold text-ash-800">
                      {ref}
                    </span>
                    <span
                      className={`shrink-0 rounded-full px-2.5 py-0.5 font-ui text-[11.5px] font-bold ${
                        top ? 'bg-brand-500 text-white' : 'bg-white text-ash-500'
                      }`}
                    >
                      {score}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </Reveal>

          {/* ── Supporting capabilities ─────────────────────────────── */}
          <ul className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-1">
            {SUPPORTING.map(({ icon, title, body }, index) => (
              <Reveal
                as="li"
                key={title}
                delay={index * 80}
                className="lift-card group flex items-start gap-4 rounded-3xl border border-ash-200 bg-white p-6 shadow-soft hover:border-brand-200 hover:shadow-card"
              >
                <span
                  aria-hidden="true"
                  className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-brand-50 text-brand-600 transition-colors duration-300 group-hover:bg-brand-500 group-hover:text-white"
                >
                  <span className="material-symbols-outlined text-[20px]">{icon}</span>
                </span>

                <div>
                  <h3 className="font-display text-[15.5px] font-bold tracking-[-0.01em] text-ash-900">
                    {title}
                  </h3>
                  <p className="mt-2 font-prose text-[13.5px] leading-[1.66] text-ash-600">
                    {body}
                  </p>
                </div>
              </Reveal>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
};

export default CapabilityGrid;
