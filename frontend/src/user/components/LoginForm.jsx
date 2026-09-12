import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import GoogleAuthButton from './auth/GoogleAuthButton';

const LoginForm = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg('');
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
        setErrorMsg(err.detail || 'Invalid Email or Password.');
      }
    } catch (error) {
      console.error('Login error:', error);
      setErrorMsg('Failed to communicate with the authentication server.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-16 flex flex-col justify-center">
      {/* Header */}
      <div className="mb-10 pb-10 flex flex-col gap-2">
        <h1 className="font-headline font-normal text-[30px] leading-9 text-[#191C1E]">
          Welcome Back
        </h1>
        <p className="font-body text-sm leading-5 text-[#44474D]">
          Please enter your credentials to continue.
        </p>
      </div>

      {/* Error Message */}
      {errorMsg && (
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
