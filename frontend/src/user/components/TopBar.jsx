import { useState, useRef, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import DeactivateModal from './DeactivateModal';

const TopBar = ({ onLogout, userEmail }) => {
  const [menuOpen, setMenuOpen] = useState(false);
  const [deactivateModalOpen, setDeactivateModalOpen] = useState(false);
  const menuRef = useRef(null);
  const navigate = useNavigate();

  const [currentUser, setCurrentUser] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('currentUser') || 'null');
    } catch {
      return null;
    }
  });

  useEffect(() => {
    const handleProfileUpdate = () => {
      try {
        setCurrentUser(JSON.parse(localStorage.getItem('currentUser') || 'null'));
      } catch {
        setCurrentUser(null);
      }
    };
    window.addEventListener('storage', handleProfileUpdate);
    window.addEventListener('user-profile-updated', handleProfileUpdate);
    return () => {
      window.removeEventListener('storage', handleProfileUpdate);
      window.removeEventListener('user-profile-updated', handleProfileUpdate);
    };
  }, []);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <>
      <header className="fixed top-0 right-0 left-72 z-30 bg-white/80 backdrop-blur-xl h-16 flex justify-between items-center px-12 border-b border-ash-200/70">
        <div className="flex gap-8">
          <a
            className="text-ash-900 border-b-2 border-brand-300 pb-1 serif-italic tracking-tight text-base cursor-default"
            href="#"
            onClick={(e) => e.preventDefault()}
          >
            Research
          </a>
          <Link
            className="text-ash-600 font-prose text-sm hover:text-ash-900 transition-colors pt-0.5"
            to="/"
          >
            Home
          </Link>
          <Link
            className="text-ash-600 font-prose text-sm hover:text-ash-900 transition-colors pt-0.5"
            to="/pricing"
          >
            Plans
          </Link>
        </div>

        <div className="flex items-center gap-5 relative" ref={menuRef}>
          {/* Settings shortcut button */}
          <button
            onClick={() => navigate('/settings')}
            title="Account Settings & Subscriptions"
            className="text-ash-600 hover:text-ash-900 transition-all focus:outline-none flex items-center p-1.5 rounded-lg hover:bg-ash-100"
          >
            <span className="material-symbols-outlined text-[22px]">settings</span>
          </button>

          {/* User profile avatar logo */}
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="focus:outline-none flex items-center transition-all hover:ring-2 hover:ring-brand-400/40 rounded-full group"
            title="User Profile Menu"
          >
            <div className="relative">
              <img
                src={currentUser?.avatar_url || '/assets/user.png'}
                alt="User Profile"
                onError={(e) => { e.currentTarget.src = '/assets/user.png'; }}
                className="w-9 h-9 rounded-full object-cover border-2 border-brand-400/80 shadow-sm transition-transform duration-200 group-hover:scale-105 bg-white"
              />
              <span className="absolute bottom-0 right-0 h-2 w-2 rounded-full bg-emerald-500 ring-2 ring-white" />
            </div>
          </button>

          {/* User profile dropdown */}
          {menuOpen && (
            <div className="absolute right-0 top-12 w-72 bg-white/95 backdrop-blur-xl rounded-2xl border border-ash-200 shadow-2xl p-3 flex flex-col gap-1 z-50 animate-[fadeIn_0.15s_ease-out]">
              <div className="flex items-center gap-3 p-2.5 rounded-xl bg-ash-50/80 border border-ash-100 mb-1">
                <img
                  src={currentUser?.avatar_url || '/assets/user.png'}
                  alt="User"
                  onError={(e) => { e.currentTarget.src = '/assets/user.png'; }}
                  className="w-10 h-10 rounded-full border border-ash-200 object-cover shadow-inner bg-white"
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-ui text-[13px] font-bold text-ash-900">
                    {currentUser?.name || currentUser?.username || 'Legal Counsel'}
                  </p>
                  <p className="truncate font-ui text-[11px] text-ash-500">
                    {userEmail || currentUser?.email || 'Authenticated User'}
                  </p>
                  <span className="mt-1 inline-block rounded-full bg-brand-100 px-2 py-0.2 font-ui text-[10px] font-bold uppercase tracking-wider text-brand-800">
                    {currentUser?.plan || 'Free'} Plan
                  </span>
                </div>
              </div>

              <div className="my-1 border-t border-ash-100" />

              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  navigate('/settings');
                }}
                className="flex items-center gap-3 rounded-xl px-3 py-2 text-left font-ui text-[13px] font-medium text-ash-700 transition-colors hover:bg-ash-100 hover:text-ash-900"
              >
                <span className="material-symbols-outlined text-[19px] text-ash-500">settings</span>
                <span>Account Settings</span>
              </button>

              <Link
                to="/terms"
                onClick={() => setMenuOpen(false)}
                className="flex items-center gap-3 rounded-xl px-3 py-2 font-ui text-[13px] font-medium text-ash-700 transition-colors hover:bg-ash-100 hover:text-ash-900"
              >
                <span className="material-symbols-outlined text-[19px] text-ash-500">gavel</span>
                <span>Terms & Conditions</span>
              </Link>

              <Link
                to="/privacy"
                onClick={() => setMenuOpen(false)}
                className="flex items-center gap-3 rounded-xl px-3 py-2 font-ui text-[13px] font-medium text-ash-700 transition-colors hover:bg-ash-100 hover:text-ash-900"
              >
                <span className="material-symbols-outlined text-[19px] text-ash-500">privacy_tip</span>
                <span>Privacy Policy</span>
              </Link>

              <div className="my-1 border-t border-ash-100" />

              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  setDeactivateModalOpen(true);
                }}
                className="flex items-center gap-3 rounded-xl px-3 py-2 text-left font-ui text-[12.5px] font-medium text-rose-600 transition-colors hover:bg-rose-50"
              >
                <span className="material-symbols-outlined text-[18px] text-rose-500">power_settings_new</span>
                <span>Deactivate Account</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  onLogout();
                }}
                className="flex items-center gap-3 rounded-xl px-3 py-2 text-left font-ui text-[12.5px] font-semibold text-ash-900 transition-colors hover:bg-ash-900 hover:text-white"
              >
                <span className="material-symbols-outlined text-[18px]">logout</span>
                <span>Sign Out</span>
              </button>
            </div>
          )}
        </div>
      </header>

      <DeactivateModal
        isOpen={deactivateModalOpen}
        onClose={() => setDeactivateModalOpen(false)}
        userEmail={userEmail}
      />
    </>
  );
};

export default TopBar;
