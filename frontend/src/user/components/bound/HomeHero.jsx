import { Link } from 'react-router-dom';

/**
 * The opening spread. Centre-weighted claim over a light blue bloom, with a
 * floating facsimile of a real retrieved judgment below it — the reader sees
 * the actual output before being asked for anything.
 */
const HIGHLIGHTS = [
  { icon: 'bolt', label: 'Answers in seconds' },
  { icon: 'format_quote', label: 'Every answer cited' },
  { icon: 'school', label: 'Free for students' },
];

const RESULTS = [
  { ref: 'Civil Appeal No. 23-P of 2017', score: '0.69', outcome: 'Dismissed', top: true },
  { ref: 'Civil Appeal No. 43-Q of 2018', score: '0.59', outcome: 'Dismissed' },
  { ref: 'Civil Appeal No. 42-K of 2016', score: '0.58', outcome: 'Dismissed' },
];

const HomeHero = () => {
  return (
    <section className="ground-light relative w-full overflow-hidden">
      {/* Decorative blooms. */}
      <span
        aria-hidden="true"
        className="float-y-slow pointer-events-none absolute -right-28 top-16 h-80 w-80 rounded-full bg-brand-200/35 blur-3xl"
      />
      <span
        aria-hidden="true"
        className="float-y pointer-events-none absolute -left-28 top-64 h-72 w-72 rounded-full bg-violet-600/10 blur-3xl"
      />

      <div className="relative mx-auto w-full max-w-[1200px] px-5 pb-20 pt-32 sm:px-8 sm:pt-36 lg:pb-24 lg:pt-40">
        {/* ── Claim ──────────────────────────────────────────────────── */}
        <div className="flex flex-col items-center text-center">
          <span
            className="pop-in relative inline-flex items-center gap-2 rounded-full border border-brand-100 bg-brand-50 px-4 py-1.5 font-ui text-[12.5px] font-semibold text-brand-700"
            style={{ '--i': 0 }}
          >
            <span
              aria-hidden="true"
              className="halo absolute -left-0.5 h-2 w-2 rounded-full bg-brand-500"
            />
            <span className="ml-3">Supreme Court of Pakistan · 9 reported judgments indexed</span>
          </span>

          <h1
            className="pop-in mt-8 max-w-[52rem] font-display text-[clamp(2.5rem,6.8vw,4.5rem)] font-bold leading-[1.04] tracking-[-0.038em] text-balance text-ash-900"
            style={{ '--i': 1 }}
          >
            Legal research that finds the{' '}
            <span className="grad-text">reasoning, not the keyword</span>
          </h1>

          <p
            className="pop-in mt-7 max-w-[42rem] font-prose text-[1.0625rem] leading-[1.8] text-ash-600 sm:text-lg"
            style={{ '--i': 2 }}
          >
            Ask your question in plain words. Every judgment is split into its facts, arguments,
            issues, ratio and order before it is indexed — so you get the passage that decides your
            point, with the case named beside it.
          </p>

          <div
            className="pop-in mt-10 flex w-full flex-col items-stretch gap-3.5 sm:w-auto sm:flex-row sm:items-center"
            style={{ '--i': 3 }}
          >
            <Link
              to="/signup"
              className="grad-btn group inline-flex items-center justify-center gap-2.5 rounded-full px-8 py-4 font-ui text-[15.5px] font-bold text-white shadow-glow transition-all duration-300 hover:-translate-y-0.5 hover:shadow-glow-lg active:translate-y-0"
            >
              Start researching free
              <span
                aria-hidden="true"
                className="material-symbols-outlined text-[19px] transition-transform duration-300 group-hover:translate-x-1"
              >
                arrow_forward
              </span>
            </Link>
            <Link
              to="/about"
              className="inline-flex items-center justify-center gap-2 rounded-full border border-ash-300 bg-white px-8 py-4 font-ui text-[15.5px] font-semibold text-ash-800 transition-all duration-300 hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700"
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[19px]">
                play_circle
              </span>
              See how it works
            </Link>
          </div>

          <ul
            className="pop-in mt-9 flex flex-wrap items-center justify-center gap-x-7 gap-y-3"
            style={{ '--i': 4 }}
          >
            {HIGHLIGHTS.map(({ icon, label }) => (
              <li key={label} className="inline-flex items-center gap-2 font-prose text-[14px] text-ash-600">
                <span
                  aria-hidden="true"
                  className="material-symbols-outlined text-[18px] text-mint-600"
                >
                  {icon}
                </span>
                {label}
              </li>
            ))}
          </ul>
        </div>

        {/* ── Facsimile of a real search ─────────────────────────────── */}
        <div className="pop-in mt-16 sm:mt-20" style={{ '--i': 5 }} aria-hidden="true">
          <div className="relative mx-auto max-w-[62rem]">
            {/* Glow behind the panel. */}
            <span className="grad-brand pointer-events-none absolute inset-x-10 -bottom-6 h-24 rounded-full opacity-25 blur-3xl" />

            <div className="relative overflow-hidden rounded-4xl border border-ash-200 bg-white shadow-card-lg">
              {/* Search bar */}
              <div className="flex flex-col gap-4 border-b border-ash-200 bg-ash-50 px-5 py-5 sm:flex-row sm:items-center sm:px-7">
                <span className="flex flex-1 items-center gap-3 rounded-full border border-ash-200 bg-white px-5 py-3 shadow-soft">
                  <span className="material-symbols-outlined text-[20px] text-brand-500">search</span>
                  <span className="truncate font-prose text-[14.5px] text-ash-700">
                    Is a claim relating to dower within the jurisdiction of a Family Court?
                  </span>
                </span>
                <span className="grad-btn inline-flex shrink-0 items-center justify-center gap-2 rounded-full px-6 py-3 font-ui text-[13.5px] font-bold text-white">
                  Search
                </span>
              </div>

              {/* Results + the answer */}
              <div className="grid grid-cols-1 lg:grid-cols-[0.88fr_1.12fr]">
                <ul className="divide-y divide-ash-200 border-b border-ash-200 lg:border-b-0 lg:border-r">
                  {RESULTS.map(({ ref, score, outcome, top }) => (
                    <li
                      key={ref}
                      className={`flex items-center justify-between gap-3 px-5 py-4 sm:px-7 ${
                        top ? 'bg-brand-50/60' : ''
                      }`}
                    >
                      <span className="flex min-w-0 flex-col gap-1">
                        <span className="truncate font-display text-[13.5px] font-semibold text-ash-900">
                          {ref}
                        </span>
                        <span className="font-prose text-[12px] text-ash-500">{outcome}</span>
                      </span>
                      <span
                        className={`shrink-0 rounded-full px-2.5 py-1 font-ui text-[11.5px] font-bold ${
                          top ? 'bg-brand-500 text-white' : 'bg-ash-100 text-ash-600'
                        }`}
                      >
                        {score}
                      </span>
                    </li>
                  ))}
                </ul>

                <div className="px-5 py-6 sm:px-7">
                  <span className="inline-flex items-center gap-2 rounded-full bg-brand-50 px-3 py-1 font-ui text-[11px] font-bold uppercase tracking-[0.08em] text-brand-700">
                    <span className="material-symbols-outlined text-[14px]">gavel</span>
                    Court reasoning
                  </span>

                  <p className="mt-4 font-prose text-[14.5px] leading-[1.72] text-ash-700">
                    The respondent was in exclusive possession and received <em>Ijjara</em> from the
                    tenants, and never pleaded non-payment of dower. The dispute concerned wrong
                    entries in the revenue record, which{' '}
                    <mark className="rounded bg-brand-100 px-1 text-ash-900">
                      in no way can be termed as a matter relating to dower
                    </mark>
                    .
                  </p>

                  <div className="mt-5 flex flex-wrap items-center gap-2">
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-mint-400/15 px-3 py-1 font-ui text-[11.5px] font-bold text-mint-700">
                      <span className="material-symbols-outlined text-[14px]">check_circle</span>
                      Appeal dismissed
                    </span>
                    <span className="rounded-full border border-ash-200 px-3 py-1 font-ui text-[11.5px] font-medium text-ash-500">
                      C.A. 23-P/2017
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default HomeHero;
