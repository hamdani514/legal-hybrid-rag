import { useState, useRef, useEffect } from 'react';

const TopBar = ({ onLogout, userEmail }) => {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);

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
    <header className="fixed top-0 right-0 left-72 z-30 bg-white/80 backdrop-blur-xl h-16 flex justify-between items-center px-12 border-b border-ash-200/70">
      <div className="flex gap-8">
        <a
          className="text-ash-900 border-b-2 border-brand-300 pb-1 serif-italic tracking-tight text-base cursor-default"
          href="#"
          onClick={(e) => e.preventDefault()}
        >
          Research
        </a>
        <a
          className="text-ash-600 font-prose text-sm hover:text-ash-900 transition-colors pt-0.5"
          href="#"
          onClick={(e) => e.preventDefault()}
        >
          Archives
        </a>
        <a
          className="text-ash-600 font-prose text-sm hover:text-ash-900 transition-colors pt-0.5"
          href="#"
          onClick={(e) => e.preventDefault()}
        >
          Precedents
        </a>
      </div>
      <div className="flex items-center gap-6 relative" ref={menuRef}>
        <button className="text-ash-900 opacity-80 hover:opacity-100 transition-all focus:outline-none">
          <span className="material-symbols-outlined">settings</span>
        </button>
        <button
          onClick={() => setMenuOpen(!menuOpen)}
          className="text-ash-900 opacity-80 hover:opacity-100 transition-all focus:outline-none flex items-center"
        >
          <span
            className="material-symbols-outlined"
            style={{ fontVariationSettings: "'FILL' 1" }}
          >
            account_circle
          </span>
        </button>

        {/* User profile dropdown */}
        {menuOpen && (
          <div className="absolute right-0 top-10 w-64 bg-white/95 backdrop-blur-md rounded-xl border border-ash-200 shadow-xl p-4 flex flex-col gap-3 z-50 animate-[fadeIn_0.2s_ease-out]">
            <div className="flex flex-col">
              <span className="font-prose text-xs font-semibold text-ash-600 uppercase tracking-wider">
                User Session
              </span>
              <span className="font-prose text-sm text-ash-900 font-medium truncate mt-1">
                {userEmail || 'Anonymous Legal Counsel'}
              </span>
            </div>
            <hr className="border-ash-200" />
            <button
              onClick={onLogout}
              className="w-full rounded-xl bg-red-600 py-2.5 text-center font-ui text-[12px] font-semibold text-white transition-colors duration-250 hover:bg-red-700"
            >
              Sign Out
            </button>
          </div>
        )}
      </div>
    </header>
  );
};

export default TopBar;
