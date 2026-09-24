import Reveal from '../Reveal';
import SectionOpener from './SectionOpener';
import MediaFrame from './MediaFrame';

/** Facts about the build, shown beside the prose. */
const FACTS = [
  { icon: 'gavel', label: 'Jurisdiction', value: 'Supreme Court of Pakistan' },
  { icon: 'account_tree', label: 'Divisions marked', value: 'Six per judgment' },
  { icon: 'travel_explore', label: 'Retrieval', value: 'Two-stage semantic' },
  { icon: 'memory', label: 'Embeddings', value: '384 dimensions' },
];

/**
 * Why the archive exists. Prose at reading measure with a facts card
 * alongside, and the central claim pulled out as a quote.
 */
const OriginSection = () => {
  return (
    <section aria-labelledby="origin-title" className="w-full px-5 py-20 sm:px-8 md:py-28">
      <div className="mx-auto max-w-[1200px]">
        <SectionOpener
          eyebrow="The problem"
          icon="help"
          title={<span id="origin-title">Keyword search was never built for</span>}
          accent="case law"
          align="left"
        />

        <div className="mt-12 grid grid-cols-1 gap-10 lg:grid-cols-[1fr_21rem] lg:gap-14">
          <div>
            <Reveal as="p" className="font-prose text-[1.0625rem] leading-[1.82] text-ash-600">
              A judgment is not a document about a topic. It is an argument with a shape — facts
              that set the ground, submissions that frame the contest, issues the Court chose to
              answer, reasoning that answers them, and an order that follows. Search it as one
              undivided block and the best a keyword can tell you is that your term appears
              somewhere inside.
            </Reveal>

            <Reveal
              as="p"
              delay={90}
              className="mt-6 font-prose text-[1.0625rem] leading-[1.82] text-ash-600"
            >
              That is why research on a deadline so often means opening eleven reports to find the
              two that matter. The words a judge used in 1996 are rarely the words in your
              question, and a phrase can appear in a heading, in counsel&rsquo;s rejected
              submission, or in the ratio itself — three entirely different things.
            </Reveal>

            <Reveal
              delay={170}
              className="mt-9 overflow-hidden rounded-3xl border border-brand-100 bg-brand-50 p-7 sm:p-8"
            >
              <span
                aria-hidden="true"
                className="material-symbols-outlined text-[28px] text-brand-400"
              >
                format_quote
              </span>
              <blockquote className="mt-2">
                <p className="font-display text-[1.3rem] font-semibold leading-[1.45] tracking-[-0.015em] text-ash-900 sm:text-[1.4rem]">
                  A citation is only useful if you know which part of the judgment it came from.
                </p>
              </blockquote>
            </Reveal>

            <Reveal
              as="p"
              delay={240}
              className="mt-9 font-prose text-[1.0625rem] leading-[1.82] text-ash-600"
            >
              So this archive divides first and searches second. Each reported judgment is read,
              marked into its six divisions, and indexed by meaning rather than by term. A question
              about the jurisdiction of a Family Court reaches the passage that decided the point,
              and arrives with the appeal number attached.
            </Reveal>
          </div>

          {/* Facts card, opened by the shelf it describes */}
          <Reveal
            delay={140}
            className="group self-start overflow-hidden rounded-4xl border border-ash-200 bg-white shadow-card lg:sticky lg:top-28"
          >
            <MediaFrame
              name="stacks"
              ratio="4 / 3"
              wash="ink"
              zoom
              className="sheen w-full"
            >
              <figcaption className="absolute inset-x-0 bottom-0 z-[2] p-6">
                <span className="font-ui text-[10.5px] font-bold uppercase tracking-[0.14em] text-brand-200">
                  The problem, physically
                </span>
                <span className="mt-1.5 block max-w-[22ch] font-display text-[16px] font-bold leading-[1.25] text-white">
                  Eleven reports open to find the two that matter
                </span>
              </figcaption>
            </MediaFrame>

            <div className="p-7">
            <h3 className="font-display text-[15px] font-bold tracking-[-0.01em] text-ash-900">
              At a glance
            </h3>

            <ul className="mt-5 flex flex-col gap-4">
              {FACTS.map(({ icon, label, value }) => (
                <li key={label} className="flex items-start gap-3.5">
                  <span
                    aria-hidden="true"
                    className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600"
                  >
                    <span className="material-symbols-outlined text-[18px]">{icon}</span>
                  </span>
                  <span className="flex flex-col">
                    <span className="font-prose text-[12.5px] text-ash-500">{label}</span>
                    <span className="font-display text-[14px] font-semibold text-ash-900">
                      {value}
                    </span>
                  </span>
                </li>
              ))}
            </ul>

            <p className="mt-6 border-t border-ash-200 pt-5 font-prose text-[13px] leading-[1.65] text-ash-500">
              Built as a final-year project. The retrieval pipeline, the section classifier and this
              interface were written from scratch.
            </p>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
};

export default OriginSection;
