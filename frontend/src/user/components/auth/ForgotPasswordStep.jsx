import React, { useState } from 'react';
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

  const handleSubmit = (e) => {
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

    // Simulated dispatch of OTP in UI
    setTimeout(() => {
      setLoading(false);
      onOtpSent(trimmed);
    }, 900);
  };

  return (
    <div className="flex flex-col justify-center w-full">
      {/* Step Header */}
      <div className="mb-8 flex flex-col gap-2">
        <div className="flex items-center gap-2 mb-1">
          <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-[#E9C176]/20 text-[#0D1C32] text-[10px] font-bold">
            1
          </span>
          <span className="font-body text-xs font-semibold uppercase tracking-[1.4px] text-[#A17F3B]">
            Step 1 of 3 · Recovery
          </span>
        </div>
        <h1 className="font-headline font-normal text-[28px] sm:text-[32px] leading-9 text-[#191C1E]">
          Forgot Password
        </h1>
        <p className="font-body text-sm leading-5 text-[#44474D]">
          Enter your registered email address to receive a secure 6-digit verification code.
        </p>
      </div>

      {/* Error Alert */}
      {errorMsg && (
        <div className="bg-red-50 text-red-700 p-3.5 mb-5 rounded text-xs font-body border border-red-100 flex items-center gap-2">
          <span className="material-symbols-outlined text-sm">error</span>
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Form */}
      <form onSubmit={handleSubmit} className="flex flex-col gap-5">
        <div className="flex flex-col gap-2">
          <label className="font-body text-xs font-bold leading-4 tracking-[1.2px] uppercase text-[#44474D]">
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
            className="w-full bg-[#F3F4F6] px-4 py-[13px] font-body text-base leading-[19px] text-[#191C1E] placeholder:text-[#C5C6CD] outline-none border border-transparent transition-all focus:bg-white focus:border-[#E9C176] focus:ring-2 focus:ring-[#E9C176]/20"
          />
        </div>

        {/* Security assurance note */}
        <div className="bg-[#F8F9FB] border border-[#E1E2E4] p-3.5 rounded flex items-start gap-3">
          <span className="material-symbols-outlined text-[#0D1C32] text-lg shrink-0 mt-0.5">
            verified_user
          </span>
          <p className="font-body text-xs text-[#585F6A] leading-relaxed">
            A temporary verification code will be dispatched to this mailbox. Codes remain valid for 10 minutes.
          </p>
        </div>

        {/* Action Button */}
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-[#0D1C32] text-white py-3.5 font-body font-bold text-sm leading-5 tracking-[1.4px] uppercase text-center shadow-[0_1px_2px_rgba(0,0,0,0.05)] hover:bg-black active:scale-[0.99] transition-all disabled:opacity-50 flex items-center justify-center gap-2"
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
      <div className="mt-8 pt-6 border-t border-[#EDEFE0]/80 text-center">
        <p className="font-body text-sm leading-5 text-[#44474D]">
          Remember your credentials?{' '}
          {onBackToLogin ? (
            <button
              type="button"
              onClick={onBackToLogin}
              className="font-bold text-[#191C1E] underline decoration-[#E9C176] decoration-2 underline-offset-4 hover:text-[#A17F3B] transition-colors"
            >
              Return to Login
            </button>
          ) : (
            <Link
              to="/login"
              className="font-bold text-[#191C1E] underline decoration-[#E9C176] decoration-2 underline-offset-4 hover:text-[#A17F3B] transition-colors"
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
