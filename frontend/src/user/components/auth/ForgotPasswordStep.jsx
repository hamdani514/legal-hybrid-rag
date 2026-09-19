import { useState } from 'react';
import { Link } from 'react-router-dom';

/**
 * Step 1: Forgot Password / Request OTP
 */
const ForgotPasswordStep = ({
  email,
  setEmail,
  onOtpSent,
  onBackToLogin,
}) => {
  const [errorMsg, setErrorMsg] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg('');

    const trimmed = email.trim();
    if (!trimmed) {
      setErrorMsg('Please enter your email address.');
      return;
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(trimmed)) {
      setErrorMsg('Please enter a valid corporate or legal email address.');
      return;
    }

    setLoading(true);

    try {
      const res = await fetch('/api/auth/forgot-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: trimmed }),
      });

      const data = await res.json();
      if (!res.ok) {
        setErrorMsg(data.detail || data.message || 'Failed to dispatch verification code.');
        setLoading(false);
        return;
      }

      setLoading(false);
      onOtpSent(trimmed);
    } catch (err) {
      console.error('Forgot password error:', err);
      setErrorMsg('Failed to communicate with authentication server.');
      setLoading(false);
    }
  };

  return (
    <div className="pop-in flex w-full flex-col">
      {/* Step Header */}
      <div className="mb-8 flex flex-col gap-2">
        <div className="flex items-center gap-2 mb-1">
          <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-brand-500/20 text-ash-900 text-[10px] font-bold">
            1
          </span>
          <span className="font-prose text-xs font-semibold uppercase tracking-[1.4px] text-brand-700">
            Step 1 of 3 · Recovery
          </span>
        </div>
        <h1 className="font-display font-bold tracking-[-0.025em] text-[28px] sm:text-[32px] leading-9 text-ash-900">
          Forgot Password
        </h1>
        <p className="font-prose text-sm leading-5 text-ash-600">
          Enter your registered email address to receive a secure 6-digit verification code.
        </p>
      </div>

      {/* Error Alert */}
      {errorMsg && (
        <div className="bg-red-50 text-red-700 p-3.5 mb-5 rounded text-xs font-prose border border-red-100 flex items-center gap-2">
          <span className="material-symbols-outlined text-sm">error</span>
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Form */}
      <form onSubmit={handleSubmit} className="flex flex-col gap-5">
        <div className="flex flex-col gap-2">
          <label className="font-prose text-xs font-bold leading-4 tracking-[1.2px] uppercase text-ash-600">
            Email Address
          </label>
          <input
            type="email"
            required
            autoFocus
            placeholder="counselor@firm.com"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
              if (errorMsg) setErrorMsg('');
            }}
            className="w-full rounded-xl border border-ash-200 bg-white px-4 py-3.5 font-prose text-[15px] leading-6 text-ash-900 placeholder:text-ash-400 outline-none transition-all duration-250 focus:border-brand-400 focus:ring-4 focus:ring-brand-500/12"
          />
        </div>

        {/* Security assurance note */}
        <div className="bg-white border border-ash-200 p-3.5 rounded flex items-start gap-3">
          <span className="material-symbols-outlined text-ash-900 text-lg shrink-0 mt-0.5">
            verified_user
          </span>
          <p className="font-prose text-xs text-ash-500 leading-relaxed">
            A temporary verification code will be dispatched to this mailbox. Codes remain valid for 10 minutes.
          </p>
        </div>

        {/* Action Button */}
        <button
          type="submit"
          disabled={loading}
          className="grad-btn w-full rounded-full py-4 font-ui text-[15px] font-bold text-white shadow-glow transition-all duration-300 hover:-translate-y-0.5 hover:shadow-glow-lg active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-60 disabled:translate-y-0 disabled:shadow-none flex items-center justify-center gap-2.5"
        >
          {loading ? (
            <>
              <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
              Dispatching Code...
            </>
          ) : (
            'Send Verification Code'
          )}
        </button>
      </form>

      {/* Footer Navigation */}
      <div className="mt-8 pt-6 border-t border-ash-50/80 text-center">
        <p className="font-prose text-sm leading-5 text-ash-600">
          Remember your credentials?{' '}
          {onBackToLogin ? (
            <button
              type="button"
              onClick={onBackToLogin}
              className="font-bold text-ash-900 underline decoration-brand-500 decoration-2 underline-offset-4 hover:text-brand-700 transition-colors"
            >
              Return to Login
            </button>
          ) : (
            <Link
              to="/login"
              className="font-bold text-ash-900 underline decoration-brand-500 decoration-2 underline-offset-4 hover:text-brand-700 transition-colors"
            >
              Return to Login
            </Link>
          )}
        </p>
      </div>
    </div>
  );
};

export default ForgotPasswordStep;
