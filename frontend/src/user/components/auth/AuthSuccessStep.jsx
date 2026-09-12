import React from 'react';
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
    <div className="flex flex-col items-center text-center justify-center w-full py-4">
      {/* Visual Seal / Checkmark */}
      <div className="relative mb-6">
        <div className="w-20 h-20 rounded-2xl bg-[#0D1C32] flex items-center justify-center shadow-lg border border-[#E9C176]/40">
          <span className="material-symbols-outlined text-[#E9C176] text-4xl">
            check_circle
          </span>
        </div>
        <span className="absolute -top-1 -right-1 flex h-4 w-4">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#E9C176] opacity-75"></span>
          <span className="relative inline-flex rounded-full h-4 w-4 bg-[#E9C176]"></span>
        </span>
      </div>

      {/* Text */}
      <h1 className="font-headline font-normal text-[28px] sm:text-[32px] leading-9 text-[#191C1E] mb-3">
        Password Successfully Reset
      </h1>
      <p className="font-body text-sm leading-6 text-[#44474D] max-w-[340px] mb-6">
        Your security credentials for <strong className="text-[#0D1C32]">{email || 'your account'}</strong> have been updated with bank-grade encryption.
      </p>

      {/* Security notice */}
      <div className="w-full bg-[#F8F9FB] border border-[#E1E2E4] p-3.5 rounded text-left flex items-center gap-3 mb-8">
        <span className="material-symbols-outlined text-[#A17F3B] text-lg shrink-0">
          shield
        </span>
        <span className="font-body text-xs text-[#585F6A]">
          All previous active sessions have been securely terminated. Please login with your new password.
        </span>
      </div>

      {/* Primary CTA */}
      {onDone ? (
        <button
          type="button"
          onClick={onDone}
          className="w-full bg-[#0D1C32] text-white py-3.5 font-body font-bold text-sm leading-5 tracking-[1.4px] uppercase text-center shadow-[0_1px_2px_rgba(0,0,0,0.05)] hover:bg-black active:scale-[0.99] transition-all flex items-center justify-center gap-2"
        >
          <span>Return to Login</span>
          <span className="material-symbols-outlined text-sm">arrow_forward</span>
        </button>
      ) : (
        <Link
          to="/login"
          className="w-full bg-[#0D1C32] text-white py-3.5 font-body font-bold text-sm leading-5 tracking-[1.4px] uppercase text-center shadow-[0_1px_2px_rgba(0,0,0,0.05)] hover:bg-black active:scale-[0.99] transition-all flex items-center justify-center gap-2"
        >
          <span>Return to Login</span>
          <span className="material-symbols-outlined text-sm">arrow_forward</span>
        </Link>
      )}
    </div>
  );
};

export default AuthSuccessStep;
