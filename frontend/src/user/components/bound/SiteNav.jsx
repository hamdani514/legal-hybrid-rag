import { useEffect, useState } from 'react';
import { Link, NavLink } from 'react-router-dom';

const LINKS = [
  { to: '/', label: 'Home', end: true },
  { to: '/about', label: 'How it works' },
  { to: '/faq', label: 'FAQ' },
  { to: '/contact', label: 'Contact' },
];

/**
 * White sticky header. It floats over the light masthead and gains a border
 * and blur once the page scrolls, so it never competes with the headline on
 * first paint.
 */
const SiteNav = () => {
  const [settled, setSettled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setSettled(window.scrollY > 20);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const closeMenu = () => setMenuOpen(false);

  return (
    <header
      className={`fixed inset-x-0 top-0 z-50 transition-all duration-400 ${
        settled ? 'border-b border-ash-200 bg-white/90 backdrop-blur-lg' : 'border-b border-transparent'
      }`}
    >
      <div className="mx-auto flex h-[76px] max-w-[1200px] items-center justify-between gap-6 px-5 sm:px-8">
        {/* Wordmark */}
        <Link to="/" onClick={closeMenu} className="group flex items-center gap-2.5">
          <span
            aria-hidden="true"
            className="grad-brand flex h-10 w-10 items-center justify-center rounded-xl text-white shadow-glow transition-transform duration-300 group-hover:scale-105"
          >
            <span className="material-symbols-outlined text-[21px]">balance</span>
          </span>
          <span className="font-display text-[19px] font-bold tracking-[-0.02em] text-ash-900">
            Digital<span className="grad-text">Atelier</span>
          </span>
        </Link>

        {/* Desktop nav */}
        <nav aria-label="Primary" className="hidden items-center gap-1 lg:flex">
          {LINKS.map(({ to, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `rounded-full px-4 py-2 font-ui text-[14.5px] font-medium transition-colors duration-250 ${
                  isActive
                    ? 'bg-brand-50 text-brand-700'
                    : 'text-ash-600 hover:bg-ash-50 hover:text-ash-900'
                }`
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="hidden items-center gap-2.5 lg:flex">
          <Link
            to="/login"
            className="rounded-full px-4 py-2 font-ui text-[14.5px] font-medium text-ash-600 transition-colors duration-250 hover:text-ash-900"
          >
            Sign in
          </Link>
          <Link
            to="/signup"
            className="grad-btn group inline-flex items-center gap-2 rounded-full px-6 py-2.5 font-ui text-[14px] font-bold text-white shadow-glow transition-all duration-300 hover:-translate-y-0.5 hover:shadow-glow-lg active:translate-y-0"
          >
            Get started free
            <span
              aria-hidden="true"
              className="material-symbols-outlined text-[17px] transition-transform duration-300 group-hover:translate-x-0.5"
            >
              arrow_forward
            </span>
          </Link>
        </div>

        {/* Mobile toggle */}
        <button
          type="button"
          onClick={() => setMenuOpen((open) => !open)}
          aria-expanded={menuOpen}
          aria-controls="site-nav-sheet"
          aria-label={menuOpen ? 'Close menu' : 'Open menu'}
          className="flex h-11 w-11 items-center justify-center rounded-xl border border-ash-200 bg-white text-ash-800 transition-colors duration-250 hover:border-brand-300 hover:text-brand-700 lg:hidden"
        >
          <span className="material-symbols-outlined text-[22px]" aria-hidden="true">
            {menuOpen ? 'close' : 'menu'}
          </span>
        </button>
      </div>

      {/* Mobile sheet */}
      <div
        id="site-nav-sheet"
        hidden={!menuOpen}
        className="border-t border-ash-200 bg-white lg:hidden"
      >
        <nav aria-label="Primary" className="flex flex-col gap-1 px-5 py-4 sm:px-8">
          {LINKS.map(({ to, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              onClick={closeMenu}
              className={({ isActive }) =>
                `rounded-xl px-4 py-3.5 font-ui text-[15px] font-medium transition-colors duration-200 ${
                  isActive ? 'bg-brand-50 text-brand-700' : 'text-ash-700'
                }`
              }
            >
              {label}
            </NavLink>
          ))}

          <div className="mt-3 flex flex-col gap-3 border-t border-ash-200 pt-5">
            <Link
              to="/signup"
              onClick={closeMenu}
              className="grad-btn rounded-full py-3.5 text-center font-ui text-[14.5px] font-bold text-white shadow-glow"
            >
              Get started free
            </Link>
            <Link
              to="/login"
              onClick={closeMenu}
              className="rounded-full border border-ash-300 py-3.5 text-center font-ui text-[14.5px] font-semibold text-ash-800"
            >
              Sign in
            </Link>
          </div>
        </nav>
      </div>
    </header>
  );
};

export default SiteNav;
