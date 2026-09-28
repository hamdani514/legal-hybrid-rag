import { Link } from 'react-router-dom';
import MediaFrame from './MediaFrame';

/**
 * Universal Hero Banner used across Home, About, Pricing, FAQ, and Contact pages.
 * Displays the Supreme Court photographic backdrop with page-specific messaging,
 * authority badge, primary/secondary action triggers, and highlight pills.
 */
const DEFAULT_HIGHLIGHTS = [
  { icon: 'bolt', label: 'Answers in seconds' },
  { icon: 'format_quote', label: 'Every answer cited' },
  { icon: 'school', label: 'Free for students' },
];

const HomeHero = ({
  badge = 'Supreme Court of Pakistan · 9 reported judgments indexed',
  title = 'Legal research that finds the',
  accent = 'reasoning, not the keyword',
  description = 'Ask your question in plain words. Every judgment is split into its facts, arguments, issues, ratio and order before it is indexed — so you get the passage that decides your point, with the case named beside it.',
  primaryCta = { to: '/signup', label: 'Start researching free', icon: 'arrow_forward' },
  secondaryCta = { to: '/about', label: 'See how it works', icon: 'play_circle' },
  highlights = DEFAULT_HIGHLIGHTS,
}) => {
  return (
    <section className="relative w-full overflow-hidden">
      <MediaFrame
        name="court"
        wash="brand"
        grain
        drift
        ratio={false}
        className="relative w-full overflow-hidden"
      >
        {/* Decorative blooms. */}
        <span
          aria-hidden="true"
          className="float-y-slow pointer-events-none absolute -right-28 top-16 h-80 w-80 rounded-full bg-cyan-300/20 blur-3xl"
        />
        <span
          aria-hidden="true"
          className="float-y pointer-events-none absolute -left-28 top-64 h-72 w-72 rounded-full bg-violet-600/25 blur-3xl"
        />

        <div className="relative z-[1] mx-auto w-full max-w-[1200px] px-5 pb-28 pt-32 sm:px-8 sm:pt-36 lg:pb-36 lg:pt-44">
          {/* ── Claim ──────────────────────────────────────────────────── */}
          <div className="flex flex-col items-center text-center">
            {badge && (
              <span
                className="pop-in relative inline-flex items-center gap-2 rounded-full border border-white/25 bg-white/12 px-4 py-1.5 font-ui text-[12.5px] font-semibold text-white backdrop-blur-md shadow-sm"
                style={{ '--i': 0 }}
              >
                <span
                  aria-hidden="true"
                  className="halo absolute -left-0.5 h-2 w-2 rounded-full bg-cyan-400"
                />
                <span className="ml-3">{badge}</span>
              </span>
            )}

            <h1
              className="pop-in mt-8 max-w-[54rem] font-display text-[clamp(2.5rem,6.8vw,4.5rem)] font-bold leading-[1.04] tracking-[-0.038em] text-balance text-white"
              style={{ '--i': 1 }}
            >
              {title}{' '}
              {accent && (
                <span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-300 via-sky-200 to-indigo-200">
                  {accent}
                </span>
              )}
            </h1>

            {description && (
              <p
                className="pop-in mt-7 max-w-[42rem] font-prose text-[1.0625rem] leading-[1.8] text-white/85 sm:text-lg"
                style={{ '--i': 2 }}
              >
                {description}
              </p>
            )}

            {(primaryCta || secondaryCta) && (
              <div
                className="pop-in mt-10 flex w-full flex-col items-stretch gap-3.5 sm:w-auto sm:flex-row sm:items-center"
                style={{ '--i': 3 }}
              >
                {primaryCta && (
                  <Link
                    to={primaryCta.to}
                    className="grad-btn group inline-flex items-center justify-center gap-2.5 rounded-full px-8 py-4 font-ui text-[15.5px] font-bold text-white shadow-glow transition-all duration-300 hover:-translate-y-0.5 hover:shadow-glow-lg active:translate-y-0"
                  >
                    {primaryCta.label}
                    <span
                      aria-hidden="true"
                      className="material-symbols-outlined text-[19px] transition-transform duration-300 group-hover:translate-x-1"
                    >
                      {primaryCta.icon || 'arrow_forward'}
                    </span>
                  </Link>
                )}
                {secondaryCta && (
                  <Link
                    to={secondaryCta.to}
                    className="inline-flex items-center justify-center gap-2 rounded-full border border-white/25 bg-white/10 px-8 py-4 font-ui text-[15.5px] font-semibold text-white backdrop-blur-md transition-all duration-300 hover:border-white/50 hover:bg-white/20"
                  >
                    {secondaryCta.icon && (
                      <span aria-hidden="true" className="material-symbols-outlined text-[19px]">
                        {secondaryCta.icon}
                      </span>
                    )}
                    {secondaryCta.label}
                  </Link>
                )}
              </div>
            )}

            {highlights && highlights.length > 0 && (
              <ul
                className="pop-in mt-9 flex flex-wrap items-center justify-center gap-x-7 gap-y-3"
                style={{ '--i': 4 }}
              >
                {highlights.map(({ icon, label }) => (
                  <li key={label} className="inline-flex items-center gap-2 font-prose text-[14px] text-white/80">
                    <span
                      aria-hidden="true"
                      className="material-symbols-outlined text-[18px] text-cyan-300"
                    >
                      {icon}
                    </span>
                    {label}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </MediaFrame>
    </section>
  );
};

export default HomeHero;
