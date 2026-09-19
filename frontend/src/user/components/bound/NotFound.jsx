import { Link, useLocation } from 'react-router-dom';
import SiteNav from './SiteNav';
import SiteFoot from './SiteFoot';

/**
 * The catch-all. Without it an unknown path rendered an entirely blank page,
 * which is indistinguishable from the app having crashed.
 */
const ROUTES = [
  { to: '/', icon: 'home', label: 'Home', note: 'What the archive is' },
  { to: '/welcome', icon: 'search', label: 'Workspace', note: 'Ask a legal question' },
  { to: '/faq', icon: 'quiz', label: 'FAQ', note: 'How retrieval works' },
  { to: '/contact', icon: 'mail', label: 'Contact', note: 'Write to us' },
];

const NotFound = () => {
  const { pathname } = useLocation();

  return (
    <div className="flex min-h-screen w-full flex-col bg-white">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <SiteNav />

      <main
        id="main-content"
        className="ground-light relative flex flex-1 items-center justify-center overflow-hidden px-5 py-32 sm:px-8"
      >
        <span
          aria-hidden="true"
          className="float-y-slow pointer-events-none absolute -right-28 top-10 h-80 w-80 rounded-full bg-brand-200/30 blur-3xl"
        />

        <div className="relative flex w-full max-w-[40rem] flex-col items-center text-center">
          <span className="pop-in inline-flex items-center gap-2 rounded-full border border-brand-100 bg-brand-50 px-4 py-1.5 font-ui text-[12.5px] font-semibold text-brand-700">
            <span aria-hidden="true" className="material-symbols-outlined text-[15px]">
              help
            </span>
            404 · Page not found
          </span>

          <h1
            className="pop-in mt-7 font-display text-[clamp(2.25rem,6vw,3.5rem)] font-bold leading-[1.06] tracking-[-0.035em] text-balance text-ash-900"
            style={{ '--i': 1 }}
          >
            That page isn&rsquo;t <span className="grad-text">on the shelf</span>
          </h1>

          <p
            className="pop-in mt-6 max-w-[34rem] font-prose text-[1.0625rem] leading-[1.75] text-ash-600"
            style={{ '--i': 2 }}
          >
            Nothing is served at{' '}
            <code className="rounded-md bg-ash-100 px-1.5 py-0.5 font-mono text-[14px] text-ash-700">
              {pathname}
            </code>
            . It may have moved, or the link that brought you here may be wrong.
          </p>

          <ul
            className="pop-in mt-11 grid w-full grid-cols-1 gap-3 sm:grid-cols-2"
            style={{ '--i': 3 }}
          >
            {ROUTES.map(({ to, icon, label, note }) => (
              <li key={to}>
                <Link
                  to={to}
                  className="lift-card group flex items-center gap-3.5 rounded-2xl border border-ash-200 bg-white p-4 text-left shadow-soft transition-all hover:border-brand-200 hover:shadow-card"
                >
                  <span
                    aria-hidden="true"
                    className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600 transition-colors duration-300 group-hover:bg-brand-500 group-hover:text-white"
                  >
                    <span className="material-symbols-outlined text-[19px]">{icon}</span>
                  </span>
                  <span className="flex flex-col">
                    <span className="font-display text-[14.5px] font-bold text-ash-900">
                      {label}
                    </span>
                    <span className="font-prose text-[12.5px] text-ash-500">{note}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </main>

      <SiteFoot />
    </div>
  );
};

export default NotFound;
