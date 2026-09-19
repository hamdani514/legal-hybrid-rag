import { useNavigate } from 'react-router-dom';

/**
 * The console page header. The primary action carries the brand gradient and
 * sign-out is a quiet bordered control — previously both were identical dark
 * buttons, which gave a destructive action the same weight as the main one.
 */
const AdminHeader = ({ title, subtitle, actionButtonText, onActionClick }) => {
  const navigate = useNavigate();

  const handleLogout = () => {
    localStorage.removeItem('currentAdmin');
    navigate('/admin-login');
  };

  return (
    <header className="sticky top-0 z-40 flex flex-col gap-5 border-b border-ash-200 bg-ash-50/90 px-6 py-6 backdrop-blur-lg sm:flex-row sm:items-center sm:justify-between sm:gap-8 lg:px-10">
      <div className="flex min-w-0 flex-col gap-1">
        <h1 className="truncate font-display text-[1.75rem] font-bold leading-tight tracking-[-0.03em] text-ash-900 lg:text-[2rem]">
          {title}
        </h1>
        {subtitle && (
          <p className="font-prose text-[14px] leading-5 text-ash-500">{subtitle}</p>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-2.5">
        {/* Notifications — an icon-only control still needs a name. */}
        <button
          type="button"
          aria-label="Notifications"
          className="relative flex h-10 w-10 items-center justify-center rounded-xl border border-ash-200 bg-white text-ash-500 transition-colors duration-250 hover:border-brand-300 hover:text-brand-700"
        >
          <span aria-hidden="true" className="material-symbols-outlined text-[20px]">
            notifications
          </span>
          <span
            aria-hidden="true"
            className="absolute right-2.5 top-2.5 h-1.5 w-1.5 rounded-full bg-red-600 ring-2 ring-white"
          />
        </button>

        {actionButtonText && onActionClick && (
          <button
            type="button"
            onClick={onActionClick}
            className="grad-btn inline-flex items-center gap-2 rounded-xl px-5 py-2.5 font-ui text-[13.5px] font-bold text-white shadow-glow transition-all duration-300 hover:-translate-y-0.5 hover:shadow-glow-lg active:translate-y-0"
          >
            {actionButtonText}
          </button>
        )}

        <button
          type="button"
          onClick={handleLogout}
          className="inline-flex items-center gap-1.5 rounded-xl border border-ash-200 bg-white px-4 py-2.5 font-ui text-[13.5px] font-semibold text-ash-600 transition-all duration-250 hover:border-red-300 hover:bg-red-50 hover:text-red-700"
        >
          <span aria-hidden="true" className="material-symbols-outlined text-[17px]">
            logout
          </span>
          Sign out
        </button>
      </div>
    </header>
  );
};

export default AdminHeader;
