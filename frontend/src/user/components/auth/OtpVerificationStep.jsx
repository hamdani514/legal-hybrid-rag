import React, { useState, useRef, useEffect } from 'react';

/**
 * Step 2: OTP Verification Component
 * Features 6-digit input boxes, paste handling, keyboard navigation, and countdown timer.
 */
const OtpVerificationStep = ({
  email,
  onVerified,
  onChangeEmail,
}) => {
  const OTP_LENGTH = 6;
  const [otp, setOtp] = useState(new Array(OTP_LENGTH).fill(''));
  const [errorMsg, setErrorMsg] = useState('');
  const [infoMsg, setInfoMsg] = useState('');
  const [loading, setLoading] = useState(false);
  const [countdown, setCountdown] = useState(45);
  const [canResend, setCanResend] = useState(false);

  const inputRefs = useRef([]);

  // Countdown timer for resend
  useEffect(() => {
    let timer;
    if (countdown > 0) {
      timer = setInterval(() => {
        setCountdown((prev) => prev - 1);
      }, 1000);
    } else {
      setCanResend(true);
    }
    return () => clearInterval(timer);
  }, [countdown]);

  // Focus first input on mount
  useEffect(() => {
    if (inputRefs.current[0]) {
      inputRefs.current[0].focus();
    }
  }, []);

  const handleChange = (e, index) => {
    const val = e.target.value;
    setErrorMsg('');
    setInfoMsg('');

    // Handle single digit input
    if (/^[0-9]$/.test(val)) {
      const newOtp = [...otp];
      newOtp[index] = val;
      setOtp(newOtp);

      // Auto advance to next input
      if (index < OTP_LENGTH - 1) {
        inputRefs.current[index + 1]?.focus();
      }
    } else if (val === '') {
      const newOtp = [...otp];
      newOtp[index] = '';
      setOtp(newOtp);
    }
  };

  const handleKeyDown = (e, index) => {
    if (e.key === 'Backspace') {
      if (!otp[index] && index > 0) {
        // Move back and clear previous
        const newOtp = [...otp];
        newOtp[index - 1] = '';
        setOtp(newOtp);
        inputRefs.current[index - 1]?.focus();
      }
    } else if (e.key === 'ArrowLeft' && index > 0) {
      inputRefs.current[index - 1]?.focus();
    } else if (e.key === 'ArrowRight' && index < OTP_LENGTH - 1) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handlePaste = (e) => {
    e.preventDefault();
    const pastedData = e.clipboardData.getData('text/plain').trim();
    const digitsOnly = pastedData.replace(/\D/g, '').slice(0, OTP_LENGTH);

    if (digitsOnly.length > 0) {
      const newOtp = [...otp];
      for (let i = 0; i < digitsOnly.length; i++) {
        newOtp[i] = digitsOnly[i];
      }
      setOtp(newOtp);

      // Focus slot after pasted digits
      const nextIndex = Math.min(digitsOnly.length, OTP_LENGTH - 1);
      inputRefs.current[nextIndex]?.focus();
    }
  };

  const handleResend = () => {
    if (!canResend) return;
    setOtp(new Array(OTP_LENGTH).fill(''));
    setCountdown(60);
    setCanResend(false);
    setErrorMsg('');
    setInfoMsg(`A fresh verification code was sent to ${email || 'your email'}.`);
    inputRefs.current[0]?.focus();
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    setErrorMsg('');
    const enteredCode = otp.join('');

    if (enteredCode.length < OTP_LENGTH) {
      setErrorMsg(`Please enter the complete ${OTP_LENGTH}-digit authorization code.`);
      return;
    }

    setLoading(true);

    // Simulated UI validation
    setTimeout(() => {
      setLoading(false);
      // For testing convenience: any 6-digit code or "000000" works in UI mode
      onVerified(enteredCode);
    }, 850);
  };

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
  };

  return (
    <div className="flex flex-col justify-center w-full">
      {/* Header */}
      <div className="mb-6 flex flex-col gap-2">
        <div className="flex items-center gap-2 mb-1">
          <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-[#E9C176]/20 text-[#0D1C32] text-[10px] font-bold">
            2
          </span>
          <span className="font-body text-xs font-semibold uppercase tracking-[1.4px] text-[#A17F3B]">
            Step 2 of 3 · Identity Verification
          </span>
        </div>
        <h1 className="font-headline font-normal text-[28px] sm:text-[32px] leading-9 text-[#191C1E]">
          Enter Authorization Code
        </h1>
        <div className="flex flex-wrap items-center gap-1 font-body text-sm leading-5 text-[#44474D]">
          <span>Code sent to</span>
          <strong className="text-[#0D1C32] font-semibold">{email || 'your email address'}</strong>
          {onChangeEmail && (
            <button
              type="button"
              onClick={onChangeEmail}
              className="text-[#A17F3B] hover:text-[#0D1C32] text-xs font-medium ml-1 underline transition-colors"
            >
              (Edit)
            </button>
          )}
        </div>
      </div>

      {/* Info / Alert messages */}
      {infoMsg && (
        <div className="bg-emerald-50 text-emerald-800 p-3 mb-4 rounded text-xs font-body border border-emerald-100 flex items-center gap-2">
          <span className="material-symbols-outlined text-sm">check_circle</span>
          <span>{infoMsg}</span>
        </div>
      )}
      {errorMsg && (
        <div className="bg-red-50 text-red-700 p-3 mb-4 rounded text-xs font-body border border-red-100 flex items-center gap-2">
          <span className="material-symbols-outlined text-sm">error</span>
          <span>{errorMsg}</span>
        </div>
      )}

      {/* OTP Input Grid */}
      <form onSubmit={handleSubmit} className="flex flex-col gap-6">
        <div className="flex justify-between gap-2 sm:gap-3" onPaste={handlePaste}>
          {otp.map((digit, idx) => (
            <input
              key={idx}
              ref={(el) => (inputRefs.current[idx] = el)}
              type="text"
              inputMode="numeric"
              maxLength={1}
              value={digit}
              onChange={(e) => handleChange(e, idx)}
              onKeyDown={(e) => handleKeyDown(e, idx)}
              className="w-11 h-13 sm:w-12 sm:h-14 bg-[#F3F4F6] text-center font-headline font-bold text-xl sm:text-2xl text-[#0D1C32] outline-none border border-transparent rounded transition-all focus:bg-white focus:border-[#E9C176] focus:ring-2 focus:ring-[#E9C176]/30 shadow-inner"
              style={{
                boxShadow: digit ? '0 0 0 1px rgba(233,193,118,0.5)' : 'none',
              }}
            />
          ))}
        </div>

        {/* Resend Timer section */}
        <div className="flex items-center justify-between font-body text-xs text-[#585F6A] pt-1">
          <span>Didn't receive the OTP?</span>
          {canResend ? (
            <button
              type="button"
              onClick={handleResend}
              className="font-bold text-[#0D1C32] hover:text-[#A17F3B] underline decoration-[#E9C176] transition-colors"
            >
              Resend OTP Code
            </button>
          ) : (
            <span className="text-[#76849F] flex items-center gap-1">
              <span className="material-symbols-outlined text-xs">timer</span>
              Resend in {formatTime(countdown)}
            </span>
          )}
        </div>

        {/* Submit button */}
        <button
          type="submit"
          disabled={loading || otp.join('').length < OTP_LENGTH}
          className="w-full bg-[#0D1C32] text-white py-3.5 font-body font-bold text-sm leading-5 tracking-[1.4px] uppercase text-center shadow-[0_1px_2px_rgba(0,0,0,0.05)] hover:bg-black active:scale-[0.99] transition-all disabled:opacity-50 flex items-center justify-center gap-2"
        >
          {loading ? (
            <>
              <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
              Authenticating Code...
            </>
          ) : (
            'Verify & Continue'
          )}
        </button>
      </form>

      {/* Back button */}
      {onChangeEmail && (
        <div className="mt-8 pt-6 border-t border-[#EDEFE0]/80 text-center">
          <button
            type="button"
            onClick={onChangeEmail}
            className="font-body text-xs font-semibold uppercase tracking-[1.2px] text-[#585F6A] hover:text-[#0D1C32] transition-colors flex items-center justify-center gap-1 mx-auto"
          >
            <span className="material-symbols-outlined text-sm">arrow_back</span>
            Back to Email Step
          </button>
        </div>
      )}
    </div>
  );
};

export default OtpVerificationStep;
