/**
 * SessionTimeoutModal
 *
 * Pop-up screen displayed 10 seconds before auto-logout.
 * Displays a live circular countdown timer from 10 to 0 seconds.
 * Gives the user the choice to stay logged in (extends session by 1 minute)
 * or immediately sign out.
 */
const SessionTimeoutModal = ({
  isOpen,
  countdown,
  onStayLoggedIn,
  onLogoutNow,
}) => {
  if (!isOpen) return null;

  const radius = 46;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (Math.max(0, countdown) / 10) * circumference;
  const isUrgent = countdown <= 5;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="session-timeout-heading"
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/65 backdrop-blur-md p-4 animate-in fade-in duration-200"
    >
      <div className="bg-white rounded-3xl max-w-md w-full p-8 shadow-2xl border border-[#E2E8F0] flex flex-col items-center text-center relative animate-in zoom-in-95 duration-200">
        
        {/* Security Badge */}
        <div className="inline-flex items-center gap-1.5 px-3.5 py-1 rounded-full bg-amber-500/10 border border-amber-500/25 text-amber-700 text-[11px] font-bold tracking-wider uppercase mb-3">
          <span className="material-symbols-outlined text-[15px] text-amber-600 animate-pulse">
            lock_clock
          </span>
          Security Auto-Logout
        </div>

        {/* Circular Countdown Progress Ring */}
        <div className="relative w-32 h-32 flex items-center justify-center my-3">
          <svg className="w-full h-full -rotate-90 transform" viewBox="0 0 108 108">
            {/* Background Track */}
            <circle
              cx="54"
              cy="54"
              r={radius}
              stroke="#F1F5F9"
              strokeWidth="7"
              fill="transparent"
            />
            {/* Active Depleting Ring */}
            <circle
              cx="54"
              cy="54"
              r={radius}
              stroke={isUrgent ? '#EF4444' : '#E9C176'}
              strokeWidth="7"
              strokeDasharray={circumference}
              strokeDashoffset={strokeDashoffset}
              strokeLinecap="round"
              fill="transparent"
              className="transition-all duration-1000 ease-linear"
            />
          </svg>

          {/* Centered Big Timer Digits */}
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span
              className={`text-4xl font-headline font-black tracking-tight ${
                isUrgent ? 'text-red-600 animate-pulse' : 'text-[#0D1C32]'
              }`}
            >
              {countdown}
            </span>
            <span className="text-[10px] uppercase font-bold tracking-widest text-[#76849F] mt-0.5">
              seconds
            </span>
          </div>
        </div>

        {/* Title & Explanation */}
        <h3
          id="session-timeout-heading"
          className="font-headline font-bold text-2xl text-[#0D1C32] mb-2"
        >
          Session Expiring Soon
        </h3>

        <p className="font-body text-sm text-[#44474D] leading-relaxed mb-6 max-w-sm">
          You have been logged in for 1 minute. For your security, you will be
          automatically signed out in <strong className="text-[#0D1C32]">{countdown}s</strong> unless you choose to stay.
        </p>

        {/* Action Buttons */}
        <div className="w-full flex flex-col gap-3">
          <button
            type="button"
            onClick={onStayLoggedIn}
            className="w-full py-3.5 px-6 rounded-xl bg-[#0D1C32] text-[#E9C176] font-body text-sm font-bold hover:bg-black active:scale-[0.98] transition-all duration-150 shadow-md flex items-center justify-center gap-2 hover:shadow-lg"
          >
            <span className="material-symbols-outlined text-[19px]">lock_open</span>
            Stay Logged In (+1 Min)
          </button>

          <button
            type="button"
            onClick={onLogoutNow}
            className="w-full py-2.5 px-4 rounded-xl border border-[#E2E8F0] hover:border-red-300 hover:bg-red-50 hover:text-red-700 text-[#585F6A] font-body text-xs font-semibold transition-all duration-150 flex items-center justify-center gap-1.5"
          >
            <span className="material-symbols-outlined text-[16px]">logout</span>
            Log Out Now
          </button>
        </div>

      </div>
    </div>
  );
};

export default SessionTimeoutModal;
