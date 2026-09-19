import Reveal from '../Reveal';
import SectionOpener from './SectionOpener';

/**
 * The four stages a judgment passes through, as numbered step cards. The
 * numbering is genuine sequence, so the connector line runs through it.
 */
const STAGES = [
  {
    icon: 'upload_file',
    title: 'Ingest',
    body: 'Judgments are extracted to text, with optical recognition for scanned volumes. A content hash rejects anything already indexed.',
  },
  {
    icon: 'account_tree',
    title: 'Divide',
    body: 'A classifier marks each judgment’s six divisions, so the bench and counsel list never compete with the reasoning for a match.',
  },
  {
    icon: 'travel_explore',
    title: 'Retrieve',
    body: 'Your question becomes a vector, matched in two passes — first to narrow to the right judgments, then to find the passages inside them.',
  },
  {
    icon: 'task_alt',
    title: 'Report',
    body: 'Passages are reassembled in reading order and answered with the authority named, or reported as absent from the record.',
  },
];

/** The six divisions marked per judgment, in the order a judgment reads. */
const DIVISIONS = [
  { label: 'Header & Coram', note: 'Bench, parties, counsel' },
  { label: 'Facts', note: 'The narrative below' },
  { label: 'Arguments', note: 'Counsel submissions' },
  { label: 'Legal Issues', note: 'Questions framed' },
  { label: 'Analysis & Ratio', note: 'The Court’s reasoning' },
  { label: 'Final Order', note: 'The disposition' },
];

const MethodSection = () => {
  return (
    <section aria-labelledby="method-title" className="w-full px-5 py-20 sm:px-8 md:py-28">
      <div className="mx-auto max-w-[1200px]">
        <SectionOpener
          eyebrow="How it works"
          icon="route"
          title={<span id="method-title">From bound volume to</span>}
          accent="cited answer"
          lede="Retrieval is only as good as the structure beneath it. Nothing is searched until it has been taken apart."
          className="mx-auto"
        />

        {/* Step cards ---------------------------------------------------- */}
        <div className="relative mt-14 md:mt-20">
          {/* Connector running behind the numbers at desktop width. */}
          <span
            aria-hidden="true"
            className="pointer-events-none absolute left-0 right-0 top-[3.25rem] hidden h-px bg-gradient-to-r from-brand-200 via-brand-300 to-violet-600/30 lg:block"
          />

          <ol className="relative grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {STAGES.map(({ icon, title, body }, index) => (
              <Reveal
                as="li"
                key={title}
                delay={index * 90}
                className="lift-card group flex flex-col rounded-3xl border border-ash-200 bg-white p-7 shadow-soft hover:border-brand-200 hover:shadow-card"
              >
                <div className="flex items-center gap-3">
                  <span
                    aria-hidden="true"
                    className="grad-brand flex h-11 w-11 items-center justify-center rounded-full font-display text-[15px] font-bold text-white shadow-glow"
                  >
                    {index + 1}
                  </span>
                  <span
                    aria-hidden="true"
                    className="flex h-10 w-10 items-center justify-center rounded-2xl bg-brand-50 text-brand-600 transition-colors duration-300 group-hover:bg-brand-100"
                  >
                    <span className="material-symbols-outlined text-[20px]">{icon}</span>
                  </span>
                </div>

                <h3 className="mt-6 font-display text-[20px] font-bold tracking-[-0.015em] text-ash-900">
                  {title}
                </h3>

                <p className="mt-3 font-prose text-[14.5px] leading-[1.7] text-ash-600">{body}</p>
              </Reveal>
            ))}
          </ol>
        </div>

        {/* Divisions panel ---------------------------------------------- */}
        <Reveal
          delay={120}
          className="mt-6 grid grid-cols-1 gap-8 overflow-hidden rounded-4xl border border-ash-200 bg-ash-50 p-8 sm:p-11 lg:grid-cols-[0.85fr_1.15fr] lg:gap-14"
        >
          <div>
            <span className="inline-flex items-center gap-2 rounded-full border border-brand-100 bg-white px-4 py-1.5 font-ui text-[12.5px] font-semibold text-brand-700">
              <span className="material-symbols-outlined text-[15px]" aria-hidden="true">
                segment
              </span>
              Why it is divided
            </span>

            <h3 className="mt-6 font-display text-[clamp(1.625rem,3.2vw,2.125rem)] font-bold leading-[1.14] tracking-[-0.025em] text-ash-900">
              Structure is what makes an answer <span className="grad-text">citable</span>
            </h3>

            <p className="mt-5 max-w-[34rem] font-prose text-[15.5px] leading-[1.75] text-ash-600">
              Search a judgment as one block and a match tells you only that the case is nearby.
              Mark its divisions and the match tells you the ratio, the order it produced, and the
              facts that carried it.
            </p>
          </div>

          <ul className="grid grid-cols-1 gap-3 self-center sm:grid-cols-2">
            {DIVISIONS.map(({ label, note }, index) => (
              <Reveal
                as="li"
                key={label}
                variant="fade"
                delay={180 + index * 60}
                className="group flex items-start gap-3 rounded-2xl border border-ash-200 bg-white px-4 py-3.5 transition-all duration-300 hover:border-brand-200 hover:shadow-soft"
              >
                <span
                  aria-hidden="true"
                  className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-50 text-brand-600 transition-colors duration-300 group-hover:bg-brand-500 group-hover:text-white"
                >
                  <span className="material-symbols-outlined text-[13px]">check</span>
                </span>
                <span className="flex flex-col">
                  <span className="font-display text-[13.5px] font-bold text-ash-900">{label}</span>
                  <span className="font-prose text-[12.5px] leading-5 text-ash-500">{note}</span>
                </span>
              </Reveal>
            ))}
          </ul>
        </Reveal>
      </div>
    </section>
  );
};

export default MethodSection;
