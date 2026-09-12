import React, { useState } from 'react';

/**
 * Step 3: Reset / Change Password Component
 * Features password strength calculation, real-time checklist validation, and visibility toggles.
 */
const ResetPasswordStep = ({
  onPasswordReset,
  email,
}) => {
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [loading, setLoading] = useState(false);

  // Criteria validation
  const hasMinLength = newPassword.length >= 8;
  const hasMixedCase = /[a-z]/.test(newPassword) && /[A-Z]/.test(newPassword);
  const hasNumberOrSymbol = /[0-9!@#$%^&*()_+\-=[\]{};':"\\|,.<>/?]/.test(newPassword);
  const isMatch = newPassword.length > 0 && newPassword === confirmPassword;

  // Strength score: 0 to 4
  const getStrengthScore = () => {
    let score = 0;
    if (newPassword.length >= 8) score++;
    if (newPassword.length >= 12) score++;
    if (hasMixedCase) score++;
    if (hasNumberOrSymbol) score++;
    return score;
  };

  const strengthScore = getStrengthScore();

  const getStrengthLabel = () => {
    if (!newPassword) return { label: '', color: '', width: '0%' };
    if (strengthScore <= 1) return { label: 'Weak', color: 'bg-rose-500', width: '25%' };
    if (strengthScore === 2) return { label: 'Fair', color: 'bg-amber-500', width: '50%' };
    if (strengthScore === 3) return { label: 'Good', color: 'bg-blue-500', width: '75%' };
    return { label: 'Strong (Legal Grade)', color: 'bg-emerald-600', width: '100%' };
  };

  const strength = getStrengthLabel();

  const handleSubmit = (e) => {
    e.preventDefault();
    setErrorMsg('');

    if (!hasMinLength) {
      setErrorMsg('Password must be at least 8 characters long.');
      return;
    }
    if (!hasMixedCase) {
      setErrorMsg('Password must include both uppercase and lowercase letters.');
      return;
    }
    if (!hasNumberOrSymbol) {
      setErrorMsg('Password must include at least one number or symbol.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setErrorMsg('Passwords do not match. Please verify.');
      return;
    }

    setLoading(true);

    // Simulated UI update
    setTimeout(() => {
      setLoading(false);
      onPasswordReset({ email, newPassword });
    }, 900);
  };

  return (
    <div className="flex flex-col justify-center w-full">
      {/* Header */}
      <div className="mb-6 flex flex-col gap-2">
        <div className="flex items-center gap-2 mb-1">
          <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-[#E9C176]/20 text-[#0D1C32] text-[10px] font-bold">
            3
          </span>
          <span className="font-body text-xs font-semibold uppercase tracking-[1.4px] text-[#A17F3B]">
            Step 3 of 3 · Update Credentials
          </span>
        </div>
        <h1 className="font-headline font-normal text-[28px] sm:text-[32px] leading-9 text-[#191C1E]">
          Set New Password
        </h1>
        <p className="font-body text-sm leading-5 text-[#44474D]">
          Choose a secure, bank-grade passphrase for your Verdict AI workspace.
        </p>
      </div>

      {/* Error Alert */}
      {errorMsg && (
        <div className="bg-red-50 text-red-700 p-3 mb-4 rounded text-xs font-body border border-red-100 flex items-center gap-2">
          <span className="material-symbols-outlined text-sm">error</span>
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Form */}
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {/* New Password */}
        <div className="flex flex-col gap-1.5">
          <label className="font-body text-xs font-bold leading-4 tracking-[1.2px] uppercase text-[#44474D]">
            New Password
          </label>
          <div className="relative w-full">
            <input
              type={showNewPassword ? 'text' : 'password'}
              required
              autoFocus
              placeholder="••••••••••••"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-full bg-[#F3F4F6] pl-4 pr-12 py-[13px] font-body text-base leading-[19px] text-[#191C1E] placeholder:text-[#C5C6CD] outline-none border border-transparent transition-all focus:bg-white focus:border-[#E9C176] focus:ring-2 focus:ring-[#E9C176]/20"
            />
            <button
              type="button"
              onClick={() => setShowNewPassword(!showNewPassword)}
              className="absolute right-4 top-1/2 -translate-y-1/2 text-[#76849F] hover:text-[#0D1C32] transition-colors flex items-center"
              aria-label={showNewPassword ? 'Hide password' : 'Show password'}
            >
              <span className="material-symbols-outlined text-[19px]">
                {showNewPassword ? 'visibility_off' : 'visibility'}
              </span>
            </button>
          </div>

          {/* Strength Bar */}
          {newPassword && (
            <div className="mt-1 flex flex-col gap-1">
              <div className="h-1.5 w-full bg-[#E1E2E4] rounded-full overflow-hidden">
                <div
                  className={`h-full transition-all duration-300 ${strength.color}`}
                  style={{ width: strength.width }}
                />
              </div>
              <div className="flex justify-between items-center text-[11px] font-body">
                <span className="text-[#585F6A]">Password strength:</span>
                <span className="font-semibold text-[#0D1C32]">{strength.label}</span>
              </div>
            </div>
          )}
        </div>

        {/* Confirm Password */}
        <div className="flex flex-col gap-1.5">
          <label className="font-body text-xs font-bold leading-4 tracking-[1.2px] uppercase text-[#44474D]">
            Confirm New Password
          </label>
          <div className="relative w-full">
            <input
              type={showConfirmPassword ? 'text' : 'password'}
              required
              placeholder="••••••••••••"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full bg-[#F3F4F6] pl-4 pr-12 py-[13px] font-body text-base leading-[19px] text-[#191C1E] placeholder:text-[#C5C6CD] outline-none border border-transparent transition-all focus:bg-white focus:border-[#E9C176] focus:ring-2 focus:ring-[#E9C176]/20"
            />
            <button
              type="button"
              onClick={() => setShowConfirmPassword(!showConfirmPassword)}
              className="absolute right-4 top-1/2 -translate-y-1/2 text-[#76849F] hover:text-[#0D1C32] transition-colors flex items-center"
              aria-label={showConfirmPassword ? 'Hide password' : 'Show password'}
            >
              <span className="material-symbols-outlined text-[19px]">
                {showConfirmPassword ? 'visibility_off' : 'visibility'}
              </span>
            </button>
          </div>
        </div>

        {/* Criteria Checklist */}
        <div className="bg-[#F8F9FB] border border-[#E1E2E4] p-3.5 rounded flex flex-col gap-2 mt-1">
          <span className="font-body text-[11px] font-bold uppercase tracking-[1px] text-[#44474D]">
            Security Requirements
          </span>
          <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs font-body">
            <li className={`flex items-center gap-1.5 ${hasMinLength ? 'text-emerald-700 font-medium' : 'text-[#76849F]'}`}>
              <span className="material-symbols-outlined text-[15px]">
                {hasMinLength ? 'check_circle' : 'radio_button_unchecked'}
              </span>
              8+ characters
            </li>
            <li className={`flex items-center gap-1.5 ${hasMixedCase ? 'text-emerald-700 font-medium' : 'text-[#76849F]'}`}>
              <span className="material-symbols-outlined text-[15px]">
                {hasMixedCase ? 'check_circle' : 'radio_button_unchecked'}
              </span>
              Upper & lower case
            </li>
            <li className={`flex items-center gap-1.5 ${hasNumberOrSymbol ? 'text-emerald-700 font-medium' : 'text-[#76849F]'}`}>
              <span className="material-symbols-outlined text-[15px]">
                {hasNumberOrSymbol ? 'check_circle' : 'radio_button_unchecked'}
              </span>
              Number or symbol
            </li>
            <li className={`flex items-center gap-1.5 ${isMatch ? 'text-emerald-700 font-medium' : 'text-[#76849F]'}`}>
              <span className="material-symbols-outlined text-[15px]">
                {isMatch ? 'check_circle' : 'radio_button_unchecked'}
              </span>
              Passwords match
            </li>
          </ul>
        </div>

        {/* Submit button */}
        <button
          type="submit"
          disabled={loading || !hasMinLength || !isMatch}
          className="w-full bg-[#0D1C32] text-white py-3.5 font-body font-bold text-sm leading-5 tracking-[1.4px] uppercase text-center shadow-[0_1px_2px_rgba(0,0,0,0.05)] hover:bg-black active:scale-[0.99] transition-all disabled:opacity-50 flex items-center justify-center gap-2 mt-2"
        >
          {loading ? (
            <>
              <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
              Updating Credentials...
            </>
          ) : (
            'Update & Lock Password'
          )}
        </button>
      </form>
    </div>
  );
};

export default ResetPasswordStep;
