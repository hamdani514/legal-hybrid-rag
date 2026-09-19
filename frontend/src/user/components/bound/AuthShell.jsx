import { Link } from 'react-router-dom';
import AuthVisual from './AuthVisual';

/**
 * The split layout shared by every authentication screen: the consistent
 * visual panel on the left, the screen's own form on the right.
 *
 * The visual panel is hidden below `lg` — on a phone the form is the whole
 * job, and a 400px-wide decorative column would only push it below the fold.
 * A compact brand row stands in for it there.
 *
 * `steps` renders the recovery progress rail above the form; pass `current`
 * as the 1-based index of the active step. Sign in and sign up omit it.
 */
const AuthShell = ({ steps = [], current = 0, variant = 'user', children }) => {
  return (
    <div className="min-h-screen w-full bg-white lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <a className="skip-link" href="#auth-form">
        Skip to form
      </a>

      {/* Left: identical on every auth screen. */}
      <AuthVisual variant={variant} />

      {/* Right: the screen's own form. */}
      <main className="ground-light relative flex min-h-screen flex-col">
        {/* Top row — brand on small screens, exit route on all. */}
        <div className="flex items-center justify-between gap-4 px-5 pt-6 sm:px-8">
          <Link to="/" className="flex items-center gap-2.5 lg:invisible">
            <span
              aria-hidden="true"
              className="grad-brand flex h-9 w-9 items-center justify-center rounded-xl text-white shadow-glow"
            >
              <span className="material-symbols-outlined text-[19px]">balance</span>
            </span>
            <span className="font-display text-[17px] font-bold tracking-[-0.02em] text-ash-900">
              Digital<span className="grad-text">Atelier</span>
            </span>
          </Link>

          <Link
            to="/"
            className="inline-flex items-center gap-1.5 rounded-full border border-ash-200 bg-white px-4 py-2 font-ui text-[13px] font-semibold text-ash-600 transition-all duration-300 hover:border-brand-300 hover:text-brand-700"
          >
            <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
              arrow_back
            </span>
            Home
          </Link>
        </div>

        {/* The form, centred in the remaining height. */}
        <div className="flex flex-1 items-center justify-center px-5 py-10 sm:px-8 sm:py-14">
          <div id="auth-form" className="w-full max-w-[27rem]">
            {steps.length > 0 && (
              <ol className="mb-9 flex items-center gap-2" aria-label="Recovery progress">
                {steps.map((label, index) => {
                  const step = index + 1;
                  const done = step < current;
                  const active = step === current;

                  return (
                    <li key={label} className="flex flex-1 flex-col gap-2">
                      <span
                        aria-hidden="true"
                        className={`h-1 rounded-full transition-colors duration-500 ${
                          done || active ? 'grad-brand' : 'bg-ash-200'
                        }`}
                      />
                      <span
                        className={`font-ui text-[11px] font-semibold leading-4 ${
                          active ? 'text-brand-700' : done ? 'text-ash-500' : 'text-ash-400'
                        }`}
                      >
                        <span className="sr-only">
                          {done ? 'Completed: ' : active ? 'Current step: ' : 'Upcoming step: '}
                        </span>
                        {label}
                      </span>
                    </li>
                  );
                })}
              </ol>
            )}

            {children}
          </div>
        </div>

        {/* Footer note — the disclaimer belongs on every screen. */}
        <p className="px-5 pb-7 text-center font-prose text-[12px] leading-5 text-ash-500 sm:px-8">
          Research aid only. Not legal advice.{' '}
          <Link to="/terms" className="font-semibold text-ash-600 hover:text-brand-700">
            Terms
          </Link>{' '}
          ·{' '}
          <Link to="/privacy" className="font-semibold text-ash-600 hover:text-brand-700">
            Privacy
          </Link>
        </p>
      </main>
    </div>
  );
};

export default AuthShell;
