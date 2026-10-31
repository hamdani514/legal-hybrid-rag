import { Link } from 'react-router-dom';
import MediaFrame from './MediaFrame';
import useIsLoggedIn from '../../hooks/useIsLoggedIn';

/**
 * Universal Hero Banner used across Home, About, Pricing, FAQ, and Contact pages.
 * Displays the Supreme Court photographic backdrop with page-specific messaging,
 * authority badge, primary/secondary action triggers, and highlight pills.
 *
 * Same size on every page: the banner is one screen tall MINUS the divisions
 * ticker that follows it on every page (DivisionsTicker: 62px, 70px from sm),
 * so banner and ticker are both on screen on arrival. Content is centred and
 * every text block has a fixed maximum width. Without a fixed height the
 * banner followed its copy — a three-line title or a four-line description
 * made one page's banner taller than the next. Only a screen too short for the
 * content lets the banner grow, so nothing is cut off.
 */
const DEFAULT_HIGHLIGHTS = [
  { icon: '/assets/thunder.svg', label: 'Answers in seconds' },
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
  const isLoggedIn = useIsLoggedIn();
  const effectivePrimaryCta = isLoggedIn
    ? { to: '/welcome', label: 'Research Workplace', icon: 'arrow_forward' }
    : primaryCta;
  return (
    <section className="relative w-full overflow-hidden">
      <MediaFrame
        name="court"
        wash="brand"
        grain
        drift
        ratio={false}
        className="relative flex min-h-[calc(100svh-62px)] w-full items-center overflow-hidden sm:min-h-[calc(100svh-70px)]"
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

        {/* Top padding clears the navigation bar, which sits over the banner. */}
        <div className="relative z-[1] mx-auto w-full max-w-[1200px] px-5 pb-16 pt-28 sm:px-8 sm:pt-32 lg:pb-20 lg:pt-32">
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

            {(effectivePrimaryCta || secondaryCta) && (
              <div
                className="pop-in mt-10 flex w-full flex-col items-stretch gap-3.5 sm:w-auto sm:flex-row sm:items-center"
                style={{ '--i': 3 }}
              >
                {effectivePrimaryCta && (
                  <Link
                    to={effectivePrimaryCta.to}
                    className="grad-btn group inline-flex items-center justify-center gap-2.5 rounded-full px-8 py-4 font-ui text-[15.5px] font-bold text-white shadow-glow transition-all duration-300 hover:-translate-y-0.5 hover:shadow-glow-lg active:translate-y-0"
                  >
                    {effectivePrimaryCta.label}
                    <span
                      aria-hidden="true"
                      className="material-symbols-outlined text-[19px] transition-transform duration-300 group-hover:translate-x-1"
                    >
                      {effectivePrimaryCta.icon || 'arrow_forward'}
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
                {highlights.map(({ icon, label }) => {
                  const isImage =
                    typeof icon === 'string' &&
                    (icon.endsWith('.svg') || icon.startsWith('/') || icon.includes('.'));
                  return (
                    <li key={label} className="inline-flex items-center gap-2 font-prose text-[14px] text-white/80">
                      {isImage ? (
                        <img
                          src={icon}
                          alt=""
                          aria-hidden="true"
                          className="h-[18px] w-[18px] object-contain"
                        />
                      ) : typeof icon !== 'string' ? (
                        icon
                      ) : (
                        <span
                          aria-hidden="true"
                          className="material-symbols-outlined text-[18px] text-cyan-300"
                        >
                          {icon}
                        </span>
                      )}
                      {label}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      </MediaFrame>
    </section>
  );
};

export default HomeHero;
