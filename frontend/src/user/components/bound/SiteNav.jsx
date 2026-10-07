import { useEffect, useState, useRef } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { clearToken } from '../../../lib/api';

const LINKS = [
  { to: '/about', label: 'How it works' },
  { to: '/pricing', label: 'Pricing' },
  { to: '/faq', label: 'FAQ' },
  { to: '/contact', label: 'Contact' },
];

/**
 * White sticky header. It floats over the light masthead and gains a border
 * and blur once the page scrolls, so it never competes with the headline on
 * first paint. When resting over the homepage dark hero banner, it presents
 * crisp light text.
 */
const SiteNav = () => {
  const [settled, setSettled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [userDropdownOpen, setUserDropdownOpen] = useState(false);
  const userDropdownRef = useRef(null);
  const location = useLocation();
  const navigate = useNavigate();

  const HERO_PAGES = ['/', '/about', '/pricing', '/faq', '/contact'];
  const hasHero = HERO_PAGES.includes(location.pathname);
  const onDark = hasHero && !settled;

  const [currentUser, setCurrentUser] = useState(() => {
    try {
      const token = localStorage.getItem('authToken');
      const user = JSON.parse(localStorage.getItem('currentUser') || 'null');
      return token && user ? user : null;
    } catch {
      return null;
    }
  });

  useEffect(() => {
    const onScroll = () => setSettled(window.scrollY > 20);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    const handleStorage = () => {
      try {
        const token = localStorage.getItem('authToken');
        const user = JSON.parse(localStorage.getItem('currentUser') || 'null');
        setCurrentUser(token && user ? user : null);
      } catch {
        setCurrentUser(null);
      }
    };
    window.addEventListener('storage', handleStorage);
    window.addEventListener('user-profile-updated', handleStorage);
    return () => {
      window.removeEventListener('storage', handleStorage);
      window.removeEventListener('user-profile-updated', handleStorage);
    };
  }, []);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (userDropdownRef.current && !userDropdownRef.current.contains(event.target)) {
        setUserDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const closeMenu = () => {
    setMenuOpen(false);
    setUserDropdownOpen(false);
  };

  const handleLogout = () => {
    clearToken();
    try {
      localStorage.removeItem('currentUser');
    } catch {}
    setCurrentUser(null);
    setUserDropdownOpen(false);
    setMenuOpen(false);
    navigate('/');
  };

  return (
    <header
      className={`fixed inset-x-0 top-0 z-50 transition-all duration-400 ${
        settled
          ? 'border-b border-ash-200 bg-white/90 backdrop-blur-lg shadow-sm'
          : onDark
          ? 'border-b border-white/10 bg-ash-950/20 backdrop-blur-sm'
          : 'border-b border-ash-200/80 bg-white/90 backdrop-blur-md shadow-sm'
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
          <span className={`font-display text-[19px] font-bold tracking-[-0.02em] transition-colors duration-300 ${
            onDark ? 'text-white' : 'text-ash-900'
          }`}>
            Verdict<span className={onDark ? 'text-cyan-300' : 'grad-text'}>AI</span>
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
                    ? onDark
                      ? 'bg-white/20 text-white font-semibold shadow-sm'
                      : 'bg-brand-50 text-brand-700'
                    : onDark
                    ? 'text-white/80 hover:bg-white/10 hover:text-white'
                    : 'text-ash-600 hover:bg-ash-50 hover:text-ash-900'
                }`
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Desktop User / Auth Button */}
        {currentUser ? (
          <div className="relative hidden lg:block" ref={userDropdownRef}>
            <button
              type="button"
              onClick={() => setUserDropdownOpen(!userDropdownOpen)}
              className="flex items-center gap-3 rounded-full p-1 pl-3 transition-all hover:ring-2 hover:ring-brand-400/40 focus:outline-none group"
              aria-expanded={userDropdownOpen}
              aria-label="User profile menu"
            >
              <div className="flex flex-col text-right">
                <span className={`font-ui text-[13px] font-semibold leading-tight transition-colors ${
                  onDark ? 'text-white' : 'text-ash-900'
                }`}>
                  {currentUser.name || currentUser.username || 'Counsel'}
                </span>
                <span className={`font-ui text-[11px] font-medium ${
                  onDark ? 'text-cyan-300' : 'text-brand-600'
                }`}>
                  {currentUser.plan || 'Free'} Plan
                </span>
              </div>
              <div className="relative">
                <img
                  src={currentUser.avatar_url || '/assets/user.png'}
                  alt="Profile"
                  onError={(e) => { e.currentTarget.src = '/assets/user.png'; }}
                  className="h-10 w-10 rounded-full border-2 border-brand-400/80 object-cover shadow-sm transition-transform duration-200 group-hover:scale-105 bg-white"
                />
                <span className="absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full bg-emerald-500 ring-2 ring-white" />
              </div>
            </button>

            {/* Profile Dropdown */}
            {userDropdownOpen && (
              <div className="absolute right-0 top-12 mt-2 w-72 origin-top-right rounded-2xl border border-ash-200 bg-white/95 p-3 shadow-2xl backdrop-blur-xl z-50 animate-[fadeIn_0.15s_ease-out]">
                {/* Header User Card */}
                <div className="flex items-center gap-3 p-3 rounded-xl bg-ash-50/80 border border-ash-100">
                  <img
                    src={currentUser.avatar_url || '/assets/user.png'}
                    alt="User"
                    onError={(e) => { e.currentTarget.src = '/assets/user.png'; }}
                    className="h-11 w-11 rounded-full border border-ash-200 object-cover shadow-inner bg-white"
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-ui text-[13.5px] font-bold text-ash-900">
                      {currentUser.name || currentUser.username || 'Counselor'}
                    </p>
                    <p className="truncate font-ui text-[11.5px] text-ash-500">
                      {currentUser.email || ''}
                    </p>
                    <span className="mt-1 inline-block rounded-full bg-brand-100 px-2.5 py-0.5 font-ui text-[10px] font-bold uppercase tracking-wider text-brand-800">
                      {currentUser.plan || 'Free'} Tier
                    </span>
                  </div>
                </div>

                <div className="my-2 border-t border-ash-100" />

                {/* Navigation Links */}
                <div className="flex flex-col gap-0.5">
                  <Link
                    to="/welcome"
                    onClick={() => setUserDropdownOpen(false)}
                    className="flex items-center gap-3 rounded-xl px-3 py-2.5 font-ui text-[13px] font-medium text-ash-700 transition-colors hover:bg-ash-100 hover:text-ash-900"
                  >
                    <span className="material-symbols-outlined text-[19px] text-brand-600">balance</span>
                    <span>Research Workspace</span>
                  </Link>

                  <Link
                    to="/settings"
                    onClick={() => setUserDropdownOpen(false)}
                    className="flex items-center gap-3 rounded-xl px-3 py-2.5 font-ui text-[13px] font-medium text-ash-700 transition-colors hover:bg-ash-100 hover:text-ash-900"
                  >
                    <span className="material-symbols-outlined text-[19px] text-ash-500">settings</span>
                    <span>Settings</span>
                  </Link>

                  <Link
                    to="/terms"
                    onClick={() => setUserDropdownOpen(false)}
                    className="flex items-center gap-3 rounded-xl px-3 py-2.5 font-ui text-[13px] font-medium text-ash-700 transition-colors hover:bg-ash-100 hover:text-ash-900"
                  >
                    <span className="material-symbols-outlined text-[19px] text-ash-500">gavel</span>
                    <span>Terms & Conditions</span>
                  </Link>

                  <Link
                    to="/privacy"
                    onClick={() => setUserDropdownOpen(false)}
                    className="flex items-center gap-3 rounded-xl px-3 py-2.5 font-ui text-[13px] font-medium text-ash-700 transition-colors hover:bg-ash-100 hover:text-ash-900"
                  >
                    <span className="material-symbols-outlined text-[19px] text-ash-500">privacy_tip</span>
                    <span>Privacy Policy</span>
                  </Link>
                </div>

                <div className="my-2 border-t border-ash-100" />

                <button
                  type="button"
                  onClick={handleLogout}
                  className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 font-ui text-[13px] font-semibold text-rose-600 transition-colors hover:bg-rose-50"
                >
                  <span className="material-symbols-outlined text-[19px] text-rose-500">logout</span>
                  <span>Sign out</span>
                </button>
              </div>
            )}
          </div>
        ) : (
          <div className="hidden items-center gap-2.5 lg:flex">
            <Link
              to="/login"
              className={`rounded-full px-4 py-2 font-ui text-[14.5px] font-medium transition-colors duration-250 ${
                onDark ? 'text-white/90 hover:text-white' : 'text-ash-600 hover:text-ash-900'
              }`}
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
        )}

        {/* Mobile toggle */}
        <button
          type="button"
          onClick={() => setMenuOpen((open) => !open)}
          aria-expanded={menuOpen}
          aria-controls="site-nav-sheet"
          aria-label={menuOpen ? 'Close menu' : 'Open menu'}
          className={`flex h-11 w-11 items-center justify-center rounded-xl border transition-colors duration-250 lg:hidden ${
            onDark
              ? 'border-white/20 bg-white/10 text-white hover:bg-white/20'
              : 'border-ash-200 bg-white text-ash-800 hover:border-brand-300 hover:text-brand-700'
          }`}
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

          {currentUser ? (
            <div className="mt-3 flex flex-col gap-1.5 border-t border-ash-200 pt-4">
              <div className="flex items-center gap-3 px-3 py-2 bg-ash-50 rounded-xl mb-2">
                <img
                  src={currentUser.avatar_url || '/assets/user.png'}
                  alt="User Avatar"
                  onError={(e) => { e.currentTarget.src = '/assets/user.png'; }}
                  className="h-10 w-10 rounded-full border border-ash-300 object-cover bg-white"
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-ui text-sm font-bold text-ash-900">
                    {currentUser.name || currentUser.username}
                  </p>
                  <p className="truncate font-ui text-xs text-ash-500">
                    {currentUser.email}
                  </p>
                  <span className="inline-block mt-0.5 rounded-full bg-brand-100 px-2 py-0.2 font-ui text-[10px] font-bold text-brand-800">
                    {currentUser.plan || 'Free'} Plan
                  </span>
                </div>
              </div>

              <Link
                to="/welcome"
                onClick={closeMenu}
                className="flex items-center gap-2.5 rounded-xl px-4 py-3 font-ui text-[14.5px] font-medium text-brand-700 bg-brand-50"
              >
                <span className="material-symbols-outlined text-[19px]">balance</span>
                Research Workspace
              </Link>
              <Link
                to="/settings"
                onClick={closeMenu}
                className="flex items-center gap-2.5 rounded-xl px-4 py-3 font-ui text-[14.5px] font-medium text-ash-700 hover:bg-ash-50"
              >
                <span className="material-symbols-outlined text-[19px]">settings</span>
                Settings
              </Link>
              <Link
                to="/terms"
                onClick={closeMenu}
                className="flex items-center gap-2.5 rounded-xl px-4 py-3 font-ui text-[14.5px] font-medium text-ash-700 hover:bg-ash-50"
              >
                <span className="material-symbols-outlined text-[19px]">gavel</span>
                Terms & Conditions
              </Link>
              <Link
                to="/privacy"
                onClick={closeMenu}
                className="flex items-center gap-2.5 rounded-xl px-4 py-3 font-ui text-[14.5px] font-medium text-ash-700 hover:bg-ash-50"
              >
                <span className="material-symbols-outlined text-[19px]">privacy_tip</span>
                Privacy Policy
              </Link>
              <button
                type="button"
                onClick={handleLogout}
                className="flex items-center gap-2.5 rounded-xl px-4 py-3 font-ui text-[14.5px] font-semibold text-rose-600 hover:bg-rose-50 text-left"
              >
                <span className="material-symbols-outlined text-[19px]">logout</span>
                Sign out
              </button>
            </div>
          ) : (
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
          )}
        </nav>
      </div>
    </header>
  );
};

export default SiteNav;
