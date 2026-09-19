import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import GoogleAuthButton from './auth/GoogleAuthButton';

const LoginForm = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [loading, setLoading] = useState(false);
  const [isDeactivated, setIsDeactivated] = useState(false);
  const [deactivatedEmail, setDeactivatedEmail] = useState('');
  const [reactivateLoading, setReactivateLoading] = useState(false);
  const [showPopup, setShowPopup] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setIsDeactivated(false);
    setLoading(true);

    if (!email.trim() || !password) {
      setErrorMsg('All fields are required.');
      setLoading(false);
      return;
    }

    try {
      const res = await fetch('/api/admin/users/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email, password }),
      });

      if (res.ok) {
        const data = await res.json();
        localStorage.setItem('currentUser', JSON.stringify(data));
        navigate('/welcome');
      } else {
        const err = await res.json();
        const isDeact =
          err.is_deactivated ||
          err.detail?.toLowerCase().includes('deactivat') ||
          err.detail?.toLowerCase().includes('not active');

        if (isDeact) {
          setIsDeactivated(true);
          setDeactivatedEmail(err.email || email.trim());
          setErrorMsg('');
        } else {
          setIsDeactivated(false);
          setErrorMsg(err.detail || 'Invalid Email or Password.');
        }
      }
    } catch (error) {
      console.error('Login error:', error);
      setErrorMsg('Failed to communicate with the authentication server.');
    } finally {
      setLoading(false);
    }
  };

  const handleRequestReactivation = async () => {
    const targetEmail = deactivatedEmail || email.trim();
    if (!targetEmail) {
      setErrorMsg('Please enter your email address to receive a reactivation link.');
      return;
    }

    setReactivateLoading(true);
    setErrorMsg('');

    try {
      const res = await fetch('/api/auth/send-reactivation-link', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email: targetEmail }),
      });

      const data = await res.json();
      if (res.ok) {
        setShowPopup(true);
      } else {
        setErrorMsg(data.detail || data.message || 'Failed to dispatch reactivation email.');
      }
    } catch (err) {
      console.error('Reactivation link error:', err);
      setErrorMsg('Failed to communicate with authentication server.');
    } finally {
      setReactivateLoading(false);
    }
  };

  return (
    <div className="p-16 flex flex-col justify-center relative">
      {/* Reactivation Link Sent Modal Popup */}
      {showPopup && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4 animate-in fade-in duration-200">
          <div className="bg-white rounded-3xl max-w-md w-full p-8 shadow-2xl border border-[#E2E8F0] flex flex-col items-center text-center relative animate-in zoom-in-95 duration-200">
            <button
              type="button"
              onClick={() => setShowPopup(false)}
              className="absolute top-5 right-5 text-gray-400 hover:text-gray-700 transition-colors"
              aria-label="Close"
            >
              <span className="material-symbols-outlined text-xl">close</span>
            </button>

            <div className="w-16 h-16 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center mb-4 border border-emerald-100 shadow-sm">
              <span className="material-symbols-outlined text-3xl">mark_email_read</span>
            </div>

            <h3 className="font-headline font-bold text-2xl text-[#0D1C32] mb-2">
              Reactivation Link Sent!
            </h3>

            <p className="font-body text-sm text-[#44474D] leading-relaxed mb-4">
              A secure reactivation link has been sent to:
            </p>

            <div className="w-full bg-[#F8FAFC] border border-[#E2E8F0] rounded-xl px-4 py-2.5 mb-4 text-sm font-semibold text-[#0D1C32] break-all">
              {deactivatedEmail || email}
            </div>

            <div className="w-full bg-amber-50/70 border border-amber-200/80 rounded-xl p-3.5 text-xs font-body text-amber-950 mb-6 text-left">
              <p className="m-0 mb-1.5 font-bold flex items-center gap-1.5 text-amber-900">
                <span className="material-symbols-outlined text-base text-amber-600">info</span>
                Next Steps:
              </p>
              <ol className="list-decimal pl-4 m-0 space-y-1 text-amber-900/90 leading-relaxed">
                <li>Open your email inbox (and check spam folder).</li>
                <li>Click <strong>"Reactivate My Account & Sign In"</strong>.</li>
                <li>Your account will be restored and ready for sign in!</li>
              </ol>
            </div>

            <button
              type="button"
              onClick={() => setShowPopup(false)}
              className="w-full py-3.5 rounded-full bg-[#0D1C32] text-white font-body text-sm font-bold hover:bg-[#172D4D] active:scale-[0.98] transition-all shadow-md"
            >
              Got It, Check Email
            </button>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="mb-10 pb-10 flex flex-col gap-2">
        <h1 className="font-headline font-normal text-[30px] leading-9 text-[#191C1E]">
          Welcome Back
        </h1>
        <p className="font-body text-sm leading-5 text-[#44474D]">
          Please enter your credentials to continue.
        </p>
      </div>

      {/* Account Deactivated Prompt Banner */}
      {isDeactivated && (
        <div className="bg-amber-50/90 border border-amber-200 rounded-xl p-5 mb-5 shadow-sm">
          <div className="flex items-start gap-3.5">
            <span className="material-symbols-outlined text-amber-600 text-2xl mt-0.5">lock_clock</span>
            <div className="flex-1">
              <h4 className="font-headline font-bold text-sm text-[#0D1C32] mb-1">
                Account Deactivated
              </h4>
              <p className="font-body text-xs text-[#585F6A] leading-relaxed mb-3">
                This account is currently deactivated. Do you want to reactivate your account?
              </p>
              <button
                type="button"
                onClick={handleRequestReactivation}
                disabled={reactivateLoading}
                className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-[#0D1C32] text-[#E9C176] font-body text-xs font-bold hover:bg-[#172D4D] transition-all shadow-sm active:translate-y-0 hover:-translate-y-0.5 disabled:opacity-60"
              >
                {reactivateLoading ? (
                  <>
                    <span className="w-3.5 h-3.5 border-2 border-[#E9C176] border-t-transparent rounded-full animate-spin"></span>
                    Sending Link...
                  </>
                ) : (
                  <>
                    <span className="material-symbols-outlined text-sm">mail</span>
                    <span>Yes, Reactivate My Account</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Error Message */}
      {errorMsg && !isDeactivated && (
        <div className="bg-red-50 text-red-700 p-4 mb-4 rounded-lg text-xs font-body border border-red-100">
          ⚠️ {errorMsg}
        </div>
      )}

      {/* Form */}
      <form onSubmit={handleSubmit} className="flex flex-col gap-6">
        {/* Email Field */}
        <div className="flex flex-col gap-2">
          <label className="font-body text-xs leading-4 tracking-[1.2px] uppercase text-[#44474D]">
            Email Address
          </label>
          <input
            type="email"
            required
            placeholder="Daniyalabbas@gmail.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full bg-[#F3F4F6] px-4 py-[14px] font-body text-base leading-[19px] text-[#191C1E] placeholder:text-[#C5C6CD] outline-none border-none transition-all focus:ring-2 focus:ring-[#E9C176]"
          />
        </div>

        {/* Password Field */}
        <div className="flex flex-col gap-2">
          <div className="flex justify-between items-center">
            <label className="font-body font-bold text-xs leading-4 tracking-[1.2px] uppercase text-[#44474D]">
              Password
            </label>
            <Link
              to="/forgot-password"
              className="font-body text-xs text-[#585F6A] hover:text-[#0D1C32] hover:underline decoration-[#E9C176] transition-colors"
            >
              Forgot Password?
            </Link>
          </div>
          <div className="relative w-full">
            <input
              type={showPassword ? 'text' : 'password'}
              required
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-[#F3F4F6] pl-4 pr-12 py-[14px] font-body text-base leading-[19px] text-[#191C1E] placeholder:text-[#C5C6CD] outline-none border-none transition-all focus:ring-2 focus:ring-[#E9C176]"
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-4 top-1/2 -translate-y-1/2 text-[#C5C6CD] hover:text-[#44474D] transition-colors flex items-center"
            >
              <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
                {showPassword ? 'visibility_off' : 'visibility'}
              </span>
            </button>
          </div>
        </div>

        {/* Primary Action - Login Button */}
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-[#0D1C32] text-white py-4 font-body font-bold text-sm leading-5 tracking-[1.4px] uppercase text-center shadow-[0_1px_2px_rgba(0,0,0,0.05)] hover:bg-black active:scale-[0.98] transition-all duration-150 disabled:opacity-50"
        >
          {loading ? 'Logging in...' : 'Login'}
        </button>

        {/* OR Divider */}
        <div className="flex items-center justify-center py-1">
          <div className="flex-1 h-[1px] bg-[#E1E2E4]"></div>
          <span className="px-4 font-body font-semibold text-xs leading-4 tracking-[1.2px] uppercase text-[#76849F]">
            or
          </span>
          <div className="flex-1 h-[1px] bg-[#E1E2E4]"></div>
        </div>

        {/* Google Authentication */}
        <GoogleAuthButton text="Continue with Google" />
      </form>

      {/* Footer Link */}
      <div className="mt-8 pt-6 text-center border-t border-[#F3F4F6]">
        <p className="font-body text-sm leading-5 text-[#44474D]">
          Don't have an account?{' '}
          <Link
            to="/signup"
            className="font-bold text-[#191C1E] underline decoration-[#E9C176] decoration-2 underline-offset-4 hover:text-[#A17F3B] transition-colors"
          >
            Signup
          </Link>
        </p>
      </div>
    </div>
  );
};

export default LoginForm;
