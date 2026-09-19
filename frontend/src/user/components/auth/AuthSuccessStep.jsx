import { Link } from 'react-router-dom';

/**
 * Step 4: Auth Success State
 * Provides clear confirmation and immediate CTA back to login.
 */
const AuthSuccessStep = ({
  email,
  onDone,
}) => {
  return (
    <div className="pop-in flex w-full flex-col items-center text-center">
      {/* Visual Seal / Checkmark */}
      <div className="relative mb-6">
        <div className="w-20 h-20 rounded-2xl bg-ash-900 flex items-center justify-center shadow-lg border border-brand-500/40">
          <span className="material-symbols-outlined text-brand-500 text-4xl">
            check_circle
          </span>
        </div>
        <span className="absolute -top-1 -right-1 flex h-4 w-4">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand-500 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-4 w-4 bg-brand-500"></span>
        </span>
      </div>

      {/* Text */}
      <h1 className="font-display font-bold tracking-[-0.025em] text-[28px] sm:text-[32px] leading-9 text-ash-900 mb-3">
        Password Successfully Reset
      </h1>
      <p className="font-prose text-sm leading-6 text-ash-600 max-w-[340px] mb-6">
        Your security credentials for <strong className="text-ash-900">{email || 'your account'}</strong> have been updated with bank-grade encryption.
      </p>

      {/* Security notice */}
      <div className="w-full bg-white border border-ash-200 p-3.5 rounded text-left flex items-center gap-3 mb-8">
        <span className="material-symbols-outlined text-brand-700 text-lg shrink-0">
          shield
        </span>
        <span className="font-prose text-xs text-ash-500">
          All previous active sessions have been securely terminated. Please login with your new password.
        </span>
      </div>

      {/* Primary CTA */}
      {onDone ? (
        <button
          type="button"
          onClick={onDone}
          className="grad-btn w-full rounded-full py-4 font-ui text-[15px] font-bold text-white shadow-glow transition-all duration-300 hover:-translate-y-0.5 hover:shadow-glow-lg active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-60 disabled:translate-y-0 disabled:shadow-none flex items-center justify-center gap-2.5"
        >
          <span>Return to Login</span>
          <span className="material-symbols-outlined text-sm">arrow_forward</span>
        </button>
      ) : (
        <Link
          to="/login"
          className="grad-btn w-full rounded-full py-4 font-ui text-[15px] font-bold text-white shadow-glow transition-all duration-300 hover:-translate-y-0.5 hover:shadow-glow-lg active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-60 disabled:translate-y-0 disabled:shadow-none flex items-center justify-center gap-2.5"
        >
          <span>Return to Login</span>
          <span className="material-symbols-outlined text-sm">arrow_forward</span>
        </Link>
      )}
    </div>
  );
};

export default AuthSuccessStep;
