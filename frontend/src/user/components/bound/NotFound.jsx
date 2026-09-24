import { Link, useLocation } from 'react-router-dom';
import SiteNav from './SiteNav';
import SiteFoot from './SiteFoot';
import MediaFrame from './MediaFrame';

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

          {/* The shelf the headline is talking about. Decorative — the page
              already says everything it needs to in words. */}
          <div
            className="pop-in group mt-12 w-full"
            style={{ '--i': 4 }}
            aria-hidden="true"
          >
            <MediaFrame
              name="stacks"
              ratio="21 / 9"
              wash="ink"
              zoom
              grain
              className="ring-photo sheen rounded-4xl shadow-card-lg"
            >
              <figcaption className="absolute inset-x-0 bottom-0 z-[2] p-6 text-left sm:p-7">
                <span className="font-ui text-[10.5px] font-bold uppercase tracking-[0.14em] text-brand-200">
                  Still on the shelf
                </span>
                <span className="mt-1.5 block font-display text-[16px] font-bold leading-[1.25] text-white sm:text-[18px]">
                  Every reported judgment in the index is still one question away
                </span>
              </figcaption>
            </MediaFrame>
          </div>
        </div>
      </main>

      <SiteFoot />
    </div>
  );
};

export default NotFound;
