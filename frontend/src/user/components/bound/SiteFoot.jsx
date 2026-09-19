import { Link } from 'react-router-dom';

const COLUMNS = [
  {
    heading: 'Product',
    links: [
      { to: '/welcome', label: 'Workspace' },
      { to: '/about', label: 'How it works' },
      { to: '/faq', label: 'FAQ' },
    ],
  },
  {
    heading: 'Account',
    links: [
      { to: '/signup', label: 'Create account' },
      { to: '/login', label: 'Sign in' },
      { to: '/forgot-password', label: 'Reset password' },
    ],
  },
  {
    heading: 'Company',
    links: [
      { to: '/contact', label: 'Contact' },
      { to: '/terms', label: 'Terms of use' },
      { to: '/privacy', label: 'Privacy' },
      { to: '/disclaimer', label: 'Disclaimer' },
    ],
  },
];

const SiteFoot = () => {
  const year = new Date().getFullYear();

  return (
    <footer className="w-full border-t border-ash-200 bg-white">
      <div className="mx-auto max-w-[1200px] px-5 py-16 sm:px-8 sm:py-20">
        <div className="grid grid-cols-1 gap-12 lg:grid-cols-[1.5fr_repeat(3,1fr)] lg:gap-10">
          {/* Brand */}
          <div className="max-w-[26rem]">
            <div className="flex items-center gap-2.5">
              <span
                aria-hidden="true"
                className="grad-brand flex h-10 w-10 items-center justify-center rounded-xl text-white shadow-glow"
              >
                <span className="material-symbols-outlined text-[21px]">balance</span>
              </span>
              <span className="font-display text-[19px] font-bold tracking-[-0.02em] text-ash-900">
                Digital<span className="grad-text">Atelier</span>
              </span>
            </div>

            <p className="mt-5 font-prose text-[14.5px] leading-[1.7] text-ash-600">
              A structured research archive of reported judgments of the Supreme Court of Pakistan,
              built for advocates and law students.
            </p>

            <p className="mt-4 rounded-2xl border border-ash-200 bg-ash-50 px-4 py-3 font-prose text-[12.5px] leading-5 text-ash-500">
              Research aid only. Not legal advice, and no substitute for the original reported
              judgment.
            </p>
          </div>

          {/* Link columns */}
          {COLUMNS.map(({ heading, links }) => (
            <nav key={heading} aria-label={heading}>
              <h2 className="font-display text-[13px] font-bold uppercase tracking-[0.1em] text-ash-900">
                {heading}
              </h2>
              <ul className="mt-5 flex flex-col gap-3">
                {links.map(({ to, label }) => (
                  <li key={label}>
                    <Link
                      to={to}
                      className="font-prose text-[14.5px] text-ash-600 transition-colors duration-250 hover:text-brand-700"
                    >
                      {label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>

        <div className="mt-14 flex flex-col gap-3 border-t border-ash-200 pt-7 sm:flex-row sm:items-center sm:justify-between">
          <p className="font-prose text-[13px] text-ash-500">
            © {year} Digital Atelier · Islamabad
          </p>
          <p className="font-prose text-[13px] text-ash-500">Built as a final-year project</p>
        </div>
      </div>
    </footer>
  );
};

export default SiteFoot;
