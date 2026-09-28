import { Link } from 'react-router-dom';
import Reveal from '../Reveal';
import CardBubbles from './CardBubbles';

/**
 * ClosingCTA — Card with Organic Floating Bubbles
 *
 * Implements the user's requested bubble background style with randomly drifting
 * translucent circular glass orbs moving in multi-axis paths.
 */
const ClosingCTA = ({
  eyebrow = 'Free to start, no credit card required',
  title = 'Ready to research faster?',
  accent = 'Ask your first question.',
  lede = 'Put the legal question in plain words and read the Court’s own reasoning back, with every authority named beside the finding.',
  primary = { to: '/signup', label: 'Create free account' },
  secondary = { to: '/about', label: 'See how it works' },
}) => {
  return (
    <section aria-labelledby="closing-cta-title" className="w-full px-5 py-20 sm:px-8 md:py-28">
      <Reveal className="mx-auto max-w-[1200px]">
        <div className="relative overflow-hidden rounded-4xl bg-gradient-to-br from-[#0066f6] via-[#004ecc] to-[#1f00db] px-6 py-16 text-center shadow-2xl sm:px-12 sm:py-20">
          {/* Animated randomly drifting glass bubbles */}
          <CardBubbles tone="light" density="standard" />

          {/* Foreground Content */}
          <div className="relative z-[2] mx-auto flex max-w-[48rem] flex-col items-center">
            {/* Eyebrow Pill */}
            <span className="inline-flex items-center gap-2 rounded-full border border-white/25 bg-white/15 px-4 py-1.5 font-ui text-[12.5px] font-semibold text-white backdrop-blur-md shadow-xs">
              <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]" />
              {eyebrow}
            </span>

            {/* Main Headline */}
            <h2
              id="closing-cta-title"
              className="mt-7 font-display text-[clamp(2.15rem,5.4vw,3.65rem)] font-bold leading-[1.08] tracking-[-0.035em] text-balance text-white"
            >
              {title}{' '}
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-sky-200 via-white to-cyan-200">
                {accent}
              </span>
            </h2>

            {/* Subtitle */}
            <p className="mt-6 max-w-[40rem] font-prose text-[1.0625rem] leading-[1.78] text-white/90">
              {lede}
            </p>

            {/* Action Buttons */}
            <div className="mt-10 flex w-full flex-col items-stretch gap-3.5 sm:w-auto sm:flex-row sm:items-center">
              <Link
                to={primary.to}
                className="group inline-flex items-center justify-center gap-2.5 rounded-full bg-white px-8 py-4 font-ui text-[15.5px] font-bold text-blue-700 shadow-card transition-all duration-300 hover:-translate-y-0.5 hover:shadow-card-lg hover:bg-slate-50 active:translate-y-0"
              >
                {primary.label}
                <span
                  aria-hidden="true"
                  className="material-symbols-outlined text-[19px] transition-transform duration-300 group-hover:translate-x-1"
                >
                  arrow_forward
                </span>
              </Link>

              <Link
                to={secondary.to}
                className="inline-flex items-center justify-center gap-2 rounded-full border border-white/30 bg-white/10 px-8 py-4 font-ui text-[15.5px] font-semibold text-white backdrop-blur-md transition-all duration-300 hover:border-white/60 hover:bg-white/20 active:translate-y-0"
              >
                {secondary.label}
              </Link>
            </div>

            {/* Trust Points */}
            <p className="mt-9 flex flex-wrap items-center justify-center gap-x-6 gap-y-2.5 font-prose text-[13.5px] text-white/85">
              {['Free for verified students', 'No card required', 'Every answer cited'].map(
                (item) => (
                  <span key={item} className="inline-flex items-center gap-1.5">
                    <span
                      aria-hidden="true"
                      className="material-symbols-outlined text-[17px] text-emerald-300"
                    >
                      check_circle
                    </span>
                    {item}
                  </span>
                )
              )}
            </p>
          </div>
        </div>
      </Reveal>
    </section>
  );
};

export default ClosingCTA;
