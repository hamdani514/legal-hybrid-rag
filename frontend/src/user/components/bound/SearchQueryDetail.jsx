import { useState } from 'react';
import { Link } from 'react-router-dom';
import MediaFrame from './MediaFrame';
import Reveal from '../Reveal';
import SectionOpener from './SectionOpener';

/**
 * Facsimile showcase of real semantic retrieval:
 * Users can see how a natural question matches against judgment divisions,
 * inspect similarity scores, and read the cited Court reasoning.
 */
const SAMPLE_QUERIES = [
  {
    id: 'dower',
    label: 'Family Court Jurisdiction',
    query: 'Is a claim relating to dower within the jurisdiction of a Family Court?',
    results: [
      {
        id: 'ca-23-p',
        ref: 'Civil Appeal No. 23-P of 2017',
        score: '0.69',
        outcome: 'Dismissed',
        reasoning:
          'The respondent was in exclusive possession and received Ijjara from the tenants, and never pleaded non-payment of dower. The dispute concerned wrong entries in the revenue record, which in no way can be termed as a matter relating to dower.',
        highlight: 'in no way can be termed as a matter relating to dower',
        outcomeBadge: 'Appeal dismissed',
        citation: 'C.A. 23-P/2017',
      },
      {
        id: 'ca-43-q',
        ref: 'Civil Appeal No. 43-Q of 2018',
        score: '0.59',
        outcome: 'Dismissed',
        reasoning:
          'Section 5 of the Family Courts Act, 1964 read with the Schedule limits jurisdiction to matters arising directly from the marriage contract. Title disputes over agricultural property fall squarely within the general jurisdiction of Civil Courts.',
        highlight: 'fall squarely within the general jurisdiction of Civil Courts',
        outcomeBadge: 'Appeal dismissed',
        citation: 'C.A. 43-Q/2018',
      },
      {
        id: 'ca-42-k',
        ref: 'Civil Appeal No. 42-K of 2016',
        score: '0.58',
        outcome: 'Dismissed',
        reasoning:
          'Where the relief claimed does not directly touch the marital contract or statutory dower obligation, the exclusive jurisdiction of the civil court is not ousted by Section 5 of the Act.',
        highlight: 'exclusive jurisdiction of the civil court is not ousted',
        outcomeBadge: 'Appeal dismissed',
        citation: 'C.A. 42-K/2016',
      },
    ],
  },
  {
    id: 'limitation',
    label: 'Revenue & Limitation',
    query: 'Does section 5 of the Limitation Act apply to appeals before the Board of Revenue?',
    results: [
      {
        id: 'ca-18-l',
        ref: 'Civil Appeal No. 18-L of 2019',
        score: '0.71',
        outcome: 'Allowed',
        reasoning:
          'The Land Revenue Act contains its own self-contained code for limitation under Section 161. Unless expressly extended by the special enactment, Section 5 of the Limitation Act cannot be imported to condone gross delay.',
        highlight: 'cannot be imported to condone gross delay',
        outcomeBadge: 'Appeal allowed',
        citation: 'C.A. 18-L/2019',
      },
      {
        id: 'ca-09-i',
        ref: 'Civil Appeal No. 09-I of 2020',
        score: '0.62',
        outcome: 'Disposed',
        reasoning:
          'Sufficient cause must be demonstrated for each day of delay where condonation is sought before revenue authorities exercising quasi-judicial functions.',
        highlight: 'Sufficient cause must be demonstrated for each day of delay',
        outcomeBadge: 'Disposed of',
        citation: 'C.A. 09-I/2020',
      },
    ],
  },
];

const SearchQueryDetail = () => {
  const [activeQueryIndex, setActiveQueryIndex] = useState(0);
  const [activeResultIndex, setActiveResultIndex] = useState(0);

  const currentQueryData = SAMPLE_QUERIES[activeQueryIndex];
  const results = currentQueryData.results;
  const activeResult = results[activeResultIndex] || results[0];

  const handleSelectQuery = (index) => {
    setActiveQueryIndex(index);
    setActiveResultIndex(0);
  };

  return (
    <section
      aria-labelledby="search-detail-title"
      className="relative w-full overflow-hidden bg-gradient-to-b from-white via-ash-50/40 to-white px-5 py-20 sm:px-8 sm:py-28"
    >
      <div className="mx-auto max-w-[1200px]">
        {/* Header */}
        <SectionOpener
          eyebrow="Interactive Retrieval Demo"
          icon="travel_explore"
          title={<span id="search-detail-title">Ask in natural words, read the</span>}
          accent="Court's reasoning"
          lede="Every judgment is split into its facts, arguments, issues, and ratio before indexing — returning the exact passage that decides the question, with verified authority."
          className="mx-auto"
        />

        {/* Query selection chips */}
        <Reveal delay={60} className="mt-8 flex flex-wrap items-center justify-center gap-2.5 sm:mt-10">
          <span className="font-ui text-[12.5px] font-semibold text-ash-500">
            Sample research queries:
          </span>
          {SAMPLE_QUERIES.map((item, idx) => {
            const isSelected = idx === activeQueryIndex;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => handleSelectQuery(idx)}
                className={`inline-flex items-center gap-1.5 rounded-full px-4 py-1.5 font-ui text-[13px] font-medium transition-all duration-200 ${
                  isSelected
                    ? 'border border-brand-500 bg-brand-50 text-brand-700 shadow-sm'
                    : 'border border-ash-200 bg-white text-ash-600 hover:border-ash-300 hover:text-ash-900'
                }`}
              >
                <span
                  className={`material-symbols-outlined text-[16px] ${
                    isSelected ? 'text-brand-600' : 'text-ash-400'
                  }`}
                >
                  {isSelected ? 'check_circle' : 'search'}
                </span>
                {item.label}
              </button>
            );
          })}
        </Reveal>

        {/* ── Facsimile of search results & reasoning ── */}
        <div className="relative mx-auto mt-10 max-w-[62rem] sm:mt-14">
          {/* Ambient brand glow behind panel */}
          <span
            aria-hidden="true"
            className="grad-brand pointer-events-none absolute inset-x-10 -bottom-6 h-28 rounded-full opacity-25 blur-3xl"
          />

          {/* Tilted photographic accents on desktop */}
          <MediaFrame
            name="volume"
            eager
            wash="soft"
            ratio="1 / 1"
            className="float-y-slow ring-photo absolute -left-36 top-12 hidden w-[11.5rem] -rotate-6 rounded-3xl shadow-card-lg xl:block 2xl:-left-52 2xl:w-[14rem]"
          />
          <MediaFrame
            name="stacks"
            eager
            wash="soft"
            ratio="3 / 4"
            className="float-y ring-photo absolute -right-36 top-24 hidden w-[11rem] rotate-[5deg] rounded-3xl shadow-card-lg xl:block 2xl:-right-52 2xl:w-[13rem]"
          />

          <Reveal
            delay={100}
            className="relative overflow-hidden rounded-4xl border border-ash-200/90 bg-white shadow-card-lg"
          >
            {/* Search query input bar */}
            <div className="flex flex-col gap-3.5 border-b border-ash-200 bg-ash-50/90 px-5 py-4 sm:flex-row sm:items-center sm:px-7 sm:py-5">
              <div className="flex flex-1 items-center gap-3 rounded-full border border-ash-200 bg-white px-5 py-3 shadow-soft transition-colors focus-within:border-brand-400">
                <span className="material-symbols-outlined text-[20px] text-brand-500">search</span>
                <span className="truncate font-prose text-[14.5px] text-ash-800">
                  {currentQueryData.query}
                </span>
              </div>
              <Link
                to="/signup"
                className="grad-btn inline-flex shrink-0 items-center justify-center gap-2 rounded-full px-6 py-3 font-ui text-[13.5px] font-bold text-white shadow-glow transition-all hover:shadow-glow-lg"
              >
                Search
                <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
              </Link>
            </div>

            {/* Retrieval details: Ranked results on left, Court reasoning on right */}
            <div className="grid grid-cols-1 lg:grid-cols-[0.88fr_1.12fr]">
              {/* Results ranking list */}
              <div className="border-b border-ash-200 bg-white lg:border-b-0 lg:border-r">
                <div className="flex items-center justify-between border-b border-ash-100 bg-ash-50/50 px-5 py-2.5 sm:px-7">
                  <span className="font-ui text-[11px] font-bold uppercase tracking-[0.08em] text-ash-500">
                    Retrieved Judgments
                  </span>
                  <span className="font-ui text-[11px] font-semibold text-brand-600">
                    Similarity Score
                  </span>
                </div>
                <ul className="divide-y divide-ash-200">
                  {results.map(({ ref, score, outcome }, idx) => {
                    const isCurrent = idx === activeResultIndex;
                    return (
                      <li key={ref}>
                        <button
                          type="button"
                          onClick={() => setActiveResultIndex(idx)}
                          className={`flex w-full items-center justify-between gap-3 px-5 py-4 text-left transition-all duration-200 sm:px-7 ${
                            isCurrent
                              ? 'bg-brand-50/70 border-l-4 border-brand-500'
                              : 'hover:bg-ash-50/80 border-l-4 border-transparent'
                          }`}
                        >
                          <span className="flex min-w-0 flex-col gap-1">
                            <span
                              className={`truncate font-display text-[13.5px] font-semibold ${
                                isCurrent ? 'text-brand-900' : 'text-ash-900'
                              }`}
                            >
                              {ref}
                            </span>
                            <span className="font-prose text-[12px] text-ash-500">{outcome}</span>
                          </span>
                          <span
                            className={`shrink-0 rounded-full px-2.5 py-1 font-ui text-[11.5px] font-bold transition-colors ${
                              isCurrent ? 'bg-brand-500 text-white' : 'bg-ash-100 text-ash-600'
                            }`}
                          >
                            {score}
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>

              {/* Court reasoning details */}
              <div className="flex flex-col justify-between bg-ash-50/30 px-5 py-6 sm:px-7">
                <div>
                  <div className="flex items-center justify-between">
                    <span className="inline-flex items-center gap-2 rounded-full bg-brand-50 px-3 py-1 font-ui text-[11px] font-bold uppercase tracking-[0.08em] text-brand-700">
                      <span className="material-symbols-outlined text-[14px]">gavel</span>
                      Court reasoning
                    </span>
                    <span className="font-ui text-[11.5px] font-medium text-ash-400">
                      Ratio Decidendi
                    </span>
                  </div>

                  <p className="mt-4 font-prose text-[14.5px] leading-[1.75] text-ash-700">
                    {activeResult.reasoning.split(activeResult.highlight).map((part, i, arr) => (
                      <span key={i}>
                        {part}
                        {i < arr.length - 1 && (
                          <mark className="rounded bg-brand-100 px-1.5 py-0.5 font-medium text-ash-900">
                            {activeResult.highlight}
                          </mark>
                        )}
                      </span>
                    ))}
                  </p>
                </div>

                <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-ash-200/80 pt-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-mint-400/15 px-3 py-1 font-ui text-[11.5px] font-bold text-mint-700">
                      <span className="material-symbols-outlined text-[14px]">check_circle</span>
                      {activeResult.outcomeBadge}
                    </span>
                    <span className="rounded-full border border-ash-200 bg-white px-3 py-1 font-ui text-[11.5px] font-medium text-ash-600 shadow-2xs">
                      {activeResult.citation}
                    </span>
                  </div>

                  <Link
                    to="/signup"
                    className="inline-flex items-center gap-1 font-ui text-[12.5px] font-semibold text-brand-600 transition-colors hover:text-brand-700"
                  >
                    Try live query
                    <span className="material-symbols-outlined text-[15px]">arrow_forward</span>
                  </Link>
                </div>
              </div>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
};

export default SearchQueryDetail;
