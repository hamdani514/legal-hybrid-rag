import { Link } from 'react-router-dom';

const TopBar = ({ sidebarOpen = true, onToggleSidebar }) => {
  if (sidebarOpen) {
    return null;
  }

  return (
    <header className="fixed top-0 right-0 left-0 z-40 bg-white/80 backdrop-blur-xl h-14 flex items-center px-4 border-b border-ash-200/70 transition-all duration-300">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onToggleSidebar}
          title="Open sidebar"
          className="flex items-center justify-center h-9 w-9 rounded-xl text-ash-500 hover:text-ash-900 hover:bg-ash-100 transition-colors"
          aria-label="Open sidebar"
        >
          <span className="material-symbols-outlined text-[20px]">dock_to_left</span>
        </button>

        <Link to="/" className="group flex items-center gap-2">
          <span
            aria-hidden="true"
            className="grad-brand flex h-7 w-7 items-center justify-center rounded-lg text-white shadow-glow transition-transform duration-300 group-hover:scale-105"
          >
            <span className="material-symbols-outlined text-[16px]">balance</span>
          </span>
          <span className="font-display text-[16px] font-bold tracking-[-0.02em] text-ash-900">
            Verdict<span className="grad-text">AI</span>
          </span>
        </Link>
      </div>
    </header>
  );
};

export default TopBar;
