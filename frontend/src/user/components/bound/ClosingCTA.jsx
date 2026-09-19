import { Link } from 'react-router-dom';
import Reveal from '../Reveal';

/**
 * The closing band: one gradient panel, rounded hard, with the two routes
 * onward. Shared by every public page so the last screen is never a dead end.
 */
const ClosingCTA = ({
  eyebrow = 'Get started',
  title = 'Ready to research faster?',
  accent = 'Ask your first question.',
  lede = 'Put the legal question in plain words and read the Court’s own reasoning back, with every authority named beside the finding.',
  primary = { to: '/signup', label: 'Create free account' },
  secondary = { to: '/about', label: 'See how it works' },
}) => {
  return (
    <section aria-labelledby="closing-cta-title" className="w-full px-5 py-20 sm:px-8 md:py-28">
      <Reveal className="mx-auto max-w-[1200px]">
        <div className="grad-brand relative overflow-hidden rounded-4xl px-6 py-16 text-center sm:px-12 sm:py-20">
          {/* Decorative blooms inside the panel. */}
          <span
            aria-hidden="true"
            className="float-y pointer-events-none absolute -right-16 -top-16 h-64 w-64 rounded-full bg-white/10 blur-2xl"
          />
          <span
            aria-hidden="true"
            className="float-y-slow pointer-events-none absolute -bottom-20 -left-10 h-56 w-56 rounded-full bg-cyan-300/15 blur-2xl"
          />

          <div className="relative mx-auto flex max-w-[46rem] flex-col items-center">
            <span className="inline-flex items-center gap-2 rounded-full border border-white/25 bg-white/12 px-4 py-1.5 font-ui text-[12.5px] font-semibold text-white backdrop-blur-sm">
              <span className="material-symbols-outlined text-[15px]" aria-hidden="true">
                bolt
              </span>
              {eyebrow}
            </span>

            <h2
              id="closing-cta-title"
              className="mt-7 font-display text-[clamp(2rem,5.2vw,3.5rem)] font-bold leading-[1.08] tracking-[-0.032em] text-balance text-white"
            >
              {title}{' '}
              <span className="text-brand-100">{accent}</span>
            </h2>

            <p className="mt-6 max-w-[38rem] font-prose text-[1.0625rem] leading-[1.78] text-white/85">
              {lede}
            </p>

            <div className="mt-10 flex w-full flex-col items-stretch gap-3.5 sm:w-auto sm:flex-row sm:items-center">
              <Link
                to={primary.to}
                className="group inline-flex items-center justify-center gap-2.5 rounded-full bg-white px-8 py-4 font-ui text-[15px] font-bold text-brand-800 shadow-card transition-all duration-300 hover:-translate-y-0.5 hover:shadow-card-lg active:translate-y-0"
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
                className="inline-flex items-center justify-center rounded-full border border-white/35 px-8 py-4 font-ui text-[15px] font-semibold text-white transition-all duration-300 hover:border-white/60 hover:bg-white/10"
              >
                {secondary.label}
              </Link>
            </div>

            <p className="mt-9 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 font-prose text-[13px] text-white/70">
              {['Free for verified students', 'No card required', 'Every answer cited'].map(
                (item) => (
                  <span key={item} className="inline-flex items-center gap-1.5">
                    <span
                      aria-hidden="true"
                      className="material-symbols-outlined text-[16px] text-brand-100"
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
