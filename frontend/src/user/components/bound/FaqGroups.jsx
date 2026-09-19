import { useId, useState } from 'react';
import Reveal from '../Reveal';

/**
 * Questions grouped the way a reader arrives at them: what it is, how it
 * retrieves, what it costs, and what it does with your data. Grouping matters
 * more than a single long list — a lawyer scanning for the limits of the tool
 * should not have to read the billing answers first.
 */
const GROUPS = [
  {
    heading: 'The archive',
    items: [
      {
        q: 'What exactly is indexed?',
        a: 'Reported judgments of the Supreme Court of Pakistan. Each one is extracted to text, divided into its six parts — header and coram, facts, arguments, legal issues, analysis and ratio, final order — and indexed at the level of those parts rather than the whole document.',
      },
      {
        q: 'Is this a substitute for the reported judgment?',
        a: 'No, and it is not built to be. Everything here is a route to the authority. Before you cite a passage, open the reported judgment and read it in place — the tool gives you the appeal number precisely so you can.',
      },
      {
        q: 'Can it advise me on my case?',
        a: 'No. It reports what the Court has held in the judgments it holds. It does not apply that to your facts, predict an outcome, or draft for you. Those are matters for an advocate.',
      },
    ],
  },
  {
    heading: 'How retrieval works',
    items: [
      {
        q: 'Why does it find cases that share none of my words?',
        a: 'Because it matches meaning rather than terms. Your question is converted into a vector and compared against vectors built from the judgment text, so a question about Family Court jurisdiction can reach the judgment that decided the point even where the wording differs entirely.',
      },
      {
        q: 'What does the relevance figure beside a result mean?',
        a: 'It is the similarity between your question and the closest passage in that judgment, on a scale where higher is nearer. Treat it as an ordering, not a score out of one: it ranks results against each other reliably, but the same figure does not carry the same meaning across two different questions.',
      },
      {
        q: 'Why does it sometimes say the answer is not in the record?',
        a: 'Because it is not. If the Court decided a case on maintainability, it did not rule on the substantive point you asked about, and the honest answer is to say so. A tool that filled that gap with something plausible would be far more dangerous than one that declines.',
      },
    ],
  },
  {
    heading: 'Access and billing',
    items: [
      {
        q: 'How is student access verified?',
        a: 'By institutional email. Write from your university address and the account is confirmed for the academic year, with 25 research sessions each month at no cost.',
      },
      {
        q: 'What counts as one research session?',
        a: 'One question and everything you read from its results — opening the authorities, moving between divisions, exporting a passage. Re-reading results you already have does not consume another session.',
      },
    ],
  },
  {
    heading: 'Your data',
    items: [
      {
        q: 'Who can see my research?',
        a: 'You, and on a chambers account the seats you share a trail with. Queries and saved trails are not used to train the underlying model and are not sold or shared with third parties.',
      },
      {
        q: 'Can I delete my history?',
        a: 'Yes. A research trail can be deleted from the workspace, and deleting your account removes the stored queries with it.',
      },
    ],
  },
];

/** One question, as a rounded card that tints when open. */
const Question = ({ q, a, open, onToggle }) => {
  const base = useId();
  const triggerId = `${base}-trigger`;
  const panelId = `${base}-panel`;

  return (
    <div
      className={`overflow-hidden rounded-3xl border transition-all duration-300 ${
        open
          ? 'border-brand-200 bg-brand-50/60 shadow-card'
          : 'border-ash-200 bg-white shadow-soft hover:border-brand-200'
      }`}
    >
      <h4 className="m-0">
        <button
          id={triggerId}
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          aria-controls={panelId}
          className="group flex w-full items-start justify-between gap-5 px-6 py-5 text-left sm:px-7"
        >
          <span className="font-display text-[15.5px] font-semibold leading-snug tracking-[-0.01em] text-ash-900 sm:text-[16.5px]">
            {q}
          </span>
          <span
            aria-hidden="true"
            className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-all duration-300 ${
              open
                ? 'rotate-45 bg-brand-500 text-white'
                : 'bg-ash-100 text-ash-500 group-hover:bg-brand-100 group-hover:text-brand-700'
            }`}
          >
            <span className="material-symbols-outlined text-[18px] leading-none">add</span>
          </span>
        </button>
      </h4>

      <div
        className="grid transition-all duration-450 ease-[cubic-bezier(0.16,1,0.3,1)]"
        style={{ gridTemplateRows: open ? '1fr' : '0fr', opacity: open ? 1 : 0 }}
      >
        <div className="overflow-hidden">
          <div
            id={panelId}
            role="region"
            aria-labelledby={triggerId}
            className="px-6 pb-6 sm:px-7"
          >
            <p className="max-w-[46rem] font-prose text-[14.5px] leading-[1.78] text-ash-600">
              {a}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

const FaqGroups = () => {
  // One open question at a time, keyed globally so opening in a later group
  // closes the earlier one — the page never becomes a wall of open panels.
  const [openKey, setOpenKey] = useState(null);

  return (
    <section aria-labelledby="faq-groups-title" className="w-full px-5 py-20 sm:px-8 md:py-28">
      <div className="mx-auto max-w-[1200px]">
        <h2 id="faq-groups-title" className="sr-only">
          Frequently asked questions
        </h2>

        <div className="flex flex-col gap-14">
          {GROUPS.map(({ heading, items }, groupIndex) => (
            <div
              key={heading}
              className="grid grid-cols-1 gap-6 lg:grid-cols-[15rem_1fr] lg:gap-12"
            >
              {/* Group heading, sticky in the margin at desktop width. */}
              <Reveal className="self-start lg:sticky lg:top-28">
                <span className="inline-flex items-center gap-2 rounded-full border border-brand-100 bg-brand-50 px-4 py-1.5 font-ui text-[12.5px] font-semibold text-brand-700">
                  <span aria-hidden="true" className="font-bold tabular-nums">
                    {String(groupIndex + 1).padStart(2, '0')}
                  </span>
                  {heading}
                </span>
                <p className="mt-3 pl-1 font-prose text-[12.5px] text-ash-500">
                  {items.length} {items.length === 1 ? 'question' : 'questions'}
                </p>
              </Reveal>

              <div className="flex flex-col gap-3.5">
                {items.map((item, i) => {
                  const key = `${groupIndex}-${i}`;
                  return (
                    <Reveal key={item.q} delay={i * 60}>
                      <Question
                        q={item.q}
                        a={item.a}
                        open={openKey === key}
                        onToggle={() => setOpenKey(openKey === key ? null : key)}
                      />
                    </Reveal>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default FaqGroups;
