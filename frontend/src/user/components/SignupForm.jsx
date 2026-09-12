import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import GoogleAuthButton from './auth/GoogleAuthButton';

const SignupForm = () => {
  const [formData, setFormData] = useState({
    username: '',
    name: '',
    email: '',
    org: '',
    plan: 'Standard',
    password: '',
    confirmPassword: '',
    dob: '',
    gender: 'Male',
    phone_no: ''
  });

  const [errorMsg, setErrorMsg] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [usernameUniqueStatus, setUsernameUniqueStatus] = useState('idle');
  const [emailUniqueStatus, setEmailUniqueStatus] = useState('idle');
  const navigate = useNavigate();

  // Username availability check
  useEffect(() => {
    if (!formData.username.trim()) {
      setUsernameUniqueStatus('idle');
      return;
    }
    setUsernameUniqueStatus('checking');
    const delayDebounce = setTimeout(async () => {
      try {
        const res = await fetch(`/api/admin/users/check-username?username=${encodeURIComponent(formData.username.trim())}`);
        if (res.ok) {
          const data = await res.json();
          setUsernameUniqueStatus(data.available ? 'available' : 'taken');
        } else {
          setUsernameUniqueStatus('idle');
        }
      } catch (err) {
        console.error('Error checking username:', err);
        setUsernameUniqueStatus('idle');
      }
    }, 500);

    return () => clearTimeout(delayDebounce);
  }, [formData.username]);

  // Email availability check
  useEffect(() => {
    const emailTrim = formData.email.trim();
    if (!emailTrim || !emailTrim.toLowerCase().endsWith('@gmail.com')) {
      setEmailUniqueStatus('idle');
      return;
    }
    setEmailUniqueStatus('checking');
    const delayDebounce = setTimeout(async () => {
      try {
        const res = await fetch(`/api/admin/users/check-email?email=${encodeURIComponent(emailTrim)}`);
        if (res.ok) {
          const data = await res.json();
          setEmailUniqueStatus(data.available ? 'available' : 'taken');
        } else {
          setEmailUniqueStatus('idle');
        }
      } catch (err) {
        console.error('Error checking email:', err);
        setEmailUniqueStatus('idle');
      }
    }, 500);

    return () => clearTimeout(delayDebounce);
  }, [formData.email]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setSuccessMsg('');
    setLoading(true);

    if (
      !formData.username.trim() ||
      !formData.name.trim() ||
      !formData.email.trim() ||
      !formData.org.trim() ||
      !formData.password ||
      !formData.confirmPassword ||
      !formData.dob ||
      !formData.phone_no.trim()
    ) {
      setErrorMsg('All fields are required.');
      setLoading(false);
      return;
    }

    if (!formData.email.toLowerCase().endsWith('@gmail.com')) {
      setErrorMsg('Email must contain @gmail.com domain.');
      setLoading(false);
      return;
    }

    const pwRegex = /^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[!@#$%^&*()_+\[\]{}|;:',.<>?/`~"\\-]).{8,}$/;
    if (!pwRegex.test(formData.password)) {
      setErrorMsg('Password must be at least 8 characters long, contain a capital letter, a small letter, a number, and a special character.');
      setLoading(false);
      return;
    }

    if (formData.password !== formData.confirmPassword) {
      setErrorMsg('Password and Confirm Password do not match.');
      setLoading(false);
      return;
    }

    const dobDate = new Date(formData.dob);
    if (isNaN(dobDate.getTime())) {
      setErrorMsg('Please select a valid Date of Birth.');
      setLoading(false);
      return;
    }

    const regDate = new Date();
    let age = regDate.getFullYear() - dobDate.getFullYear();
    const monthDiff = regDate.getMonth() - dobDate.getMonth();
    if (monthDiff < 0 || (monthDiff === 0 && regDate.getDate() < dobDate.getDate())) {
      age--;
    }

    if (age < 16) {
      setErrorMsg('User must be older than 16 years from the registration date.');
      setLoading(false);
      return;
    }

    if (usernameUniqueStatus === 'taken') {
      setErrorMsg('Username is already taken.');
      setLoading(false);
      return;
    }

    if (emailUniqueStatus === 'taken') {
      setErrorMsg('Email is already registered.');
      setLoading(false);
      return;
    }

    try {
      const payload = {
        username: formData.username,
        name: formData.name,
        email: formData.email,
        org: formData.org,
        plan: formData.plan,
        password: formData.password,
        dob: formData.dob,
        gender: formData.gender,
        phone_no: formData.phone_no,
        created_at: regDate.toISOString()
      };

      const res = await fetch('/api/admin/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        setSuccessMsg('Account created successfully! Redirecting to login...');
        setTimeout(() => {
          navigate('/login');
        }, 2000);
      } else {
        const err = await res.json();
        setErrorMsg(err.detail || 'An error occurred during registration.');
      }
    } catch (error) {
      console.error('Error during registration:', error);
      setErrorMsg('Failed to communicate with the authentication server.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full max-w-[512px] flex flex-col gap-8 pb-4 mt-20">
      {/* Header */}
      <div className="flex flex-col gap-2">
        <h2 className="font-headline font-normal text-4xl leading-10 tracking-[-0.72px] text-[#0D1C32]">
          Create Account
        </h2>
        <p className="font-body text-base leading-6 text-[#44474D]">
          Enter your credentials to join the workspace.
        </p>
      </div>

      {/* Error Message */}
      {errorMsg && (
        <div className="bg-red-50 text-red-700 p-4 rounded-lg text-xs font-body border border-red-100">
          ⚠️ {errorMsg}
        </div>
      )}

      {/* Success Message */}
      {successMsg && (
        <div className="bg-green-50 text-green-700 p-4 rounded-lg text-xs font-body border border-green-100">
          ✅ {successMsg}
        </div>
      )}

      {/* Form */}
      <form onSubmit={handleSubmit} className="flex flex-col gap-[20px]">
        {/* Full Name & Username */}
        <div className="grid grid-cols-2 gap-4">
          <div className="flex flex-col gap-[6px]">
            <label className="font-body text-xs leading-4 tracking-[1.2px] uppercase text-[#44474D]">
              Full Name
            </label>
            <input
              type="text"
              required
              placeholder="e.g. Marcus Sterling"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full bg-white px-4 py-[13px] font-body text-sm leading-[17px] text-[#191C1E] placeholder:text-[#CBD5E1] outline-none transition-all focus:ring-1 focus:ring-[#E9C176]"
              style={{ boxShadow: '0px 0px 0px 1px rgba(197, 198, 205, 0.2)' }}
            />
          </div>

          <div className="flex flex-col gap-[6px]">
            <label className="font-body text-xs leading-4 tracking-[1.2px] uppercase text-[#44474D]">
              Username
            </label>
            <input
              type="text"
              required
              placeholder="e.g. marcus_s"
              value={formData.username}
              onChange={(e) => setFormData({ ...formData, username: e.target.value })}
              className="w-full bg-white px-4 py-[13px] font-body text-sm leading-[17px] text-[#191C1E] placeholder:text-[#CBD5E1] outline-none transition-all focus:ring-1 focus:ring-[#E9C176]"
              style={{ boxShadow: '0px 0px 0px 1px rgba(197, 198, 205, 0.2)' }}
            />
            {usernameUniqueStatus === 'checking' && (
              <span className="text-[10px] text-blue-500 font-body">Checking availability...</span>
            )}
            {usernameUniqueStatus === 'available' && (
              <span className="text-[10px] text-green-600 font-body">✓ Username is available</span>
            )}
            {usernameUniqueStatus === 'taken' && (
              <span className="text-[10px] text-red-500 font-body">✗ Username is already taken</span>
            )}
          </div>
        </div>

        {/* Email & Phone Number */}
        <div className="grid grid-cols-2 gap-4">
          <div className="flex flex-col gap-[6px]">
            <label className="font-body text-xs leading-4 tracking-[1.2px] uppercase text-[#44474D]">
              Email (Gmail Only)
            </label>
            <input
              type="email"
              required
              placeholder="e.g. user@gmail.com"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              className="w-full bg-white px-4 py-[13px] font-body text-sm leading-[17px] text-[#191C1E] placeholder:text-[#CBD5E1] outline-none transition-all focus:ring-1 focus:ring-[#E9C176]"
              style={{ boxShadow: '0px 0px 0px 1px rgba(197, 198, 205, 0.2)' }}
            />
            {emailUniqueStatus === 'checking' && (
              <span className="text-[10px] text-blue-500 font-body">Checking availability...</span>
            )}
            {emailUniqueStatus === 'available' && (
              <span className="text-[10px] text-green-600 font-body">✓ Email is available</span>
            )}
            {emailUniqueStatus === 'taken' && (
              <span className="text-[10px] text-red-500 font-body">✗ Email is already registered</span>
            )}
          </div>

          <div className="flex flex-col gap-[6px]">
            <label className="font-body text-xs leading-4 tracking-[1.2px] uppercase text-[#44474D]">
              Phone Number
            </label>
            <input
              type="text"
              required
              placeholder="e.g. +92 300 1234567"
              value={formData.phone_no}
              onChange={(e) => setFormData({ ...formData, phone_no: e.target.value })}
              className="w-full bg-white px-4 py-[13px] font-body text-sm leading-[17px] text-[#191C1E] placeholder:text-[#CBD5E1] outline-none transition-all focus:ring-1 focus:ring-[#E9C176]"
              style={{ boxShadow: '0px 0px 0px 1px rgba(197, 198, 205, 0.2)' }}
            />
          </div>
        </div>

        {/* Password & Confirm Password */}
        <div className="grid grid-cols-2 gap-4">
          <div className="flex flex-col gap-[6px]">
            <label className="font-body text-xs leading-4 tracking-[1.2px] uppercase text-[#44474D]">
              Password
            </label>
            <div className="relative w-full">
              <input
                type={showPassword ? 'text' : 'password'}
                required
                placeholder="••••••••"
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                className="w-full bg-white pl-4 pr-10 py-[13px] font-body text-sm leading-[17px] text-[#191C1E] placeholder:text-[#CBD5E1] outline-none transition-all focus:ring-1 focus:ring-[#E9C176]"
                style={{ boxShadow: '0px 0px 0px 1px rgba(197, 198, 205, 0.2)' }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[#CBD5E1] hover:text-[#44474D] transition-colors flex items-center"
              >
                <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
                  {showPassword ? 'visibility_off' : 'visibility'}
                </span>
              </button>
            </div>
          </div>

          <div className="flex flex-col gap-[6px]">
            <label className="font-body text-xs leading-4 tracking-[1.2px] uppercase text-[#44474D]">
              Confirm Password
            </label>
            <div className="relative w-full">
              <input
                type={showConfirmPassword ? 'text' : 'password'}
                required
                placeholder="••••••••"
                value={formData.confirmPassword}
                onChange={(e) => setFormData({ ...formData, confirmPassword: e.target.value })}
                className="w-full bg-white pl-4 pr-10 py-[13px] font-body text-sm leading-[17px] text-[#191C1E] placeholder:text-[#CBD5E1] outline-none transition-all focus:ring-1 focus:ring-[#E9C176]"
                style={{ boxShadow: '0px 0px 0px 1px rgba(197, 198, 205, 0.2)' }}
              />
              <button
                type="button"
                onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[#CBD5E1] hover:text-[#44474D] transition-colors flex items-center"
              >
                <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
                  {showConfirmPassword ? 'visibility_off' : 'visibility'}
                </span>
              </button>
            </div>
          </div>
        </div>

        {/* Organization */}
        <div className="flex flex-col gap-[6px]">
          <label className="font-body text-xs leading-4 tracking-[1.2px] uppercase text-[#44474D]">
            Organization
          </label>
          <input
            type="text"
            required
            placeholder="e.g. Sterling & Associates"
            value={formData.org}
            onChange={(e) => setFormData({ ...formData, org: e.target.value })}
            className="w-full bg-white px-4 py-[13px] font-body text-sm leading-[17px] text-[#191C1E] placeholder:text-[#CBD5E1] outline-none transition-all focus:ring-1 focus:ring-[#E9C176]"
            style={{ boxShadow: '0px 0px 0px 1px rgba(197, 198, 205, 0.2)' }}
          />
        </div>

        {/* Gender & DOB */}
        <div className="grid grid-cols-2 gap-4">
          <div className="flex flex-col gap-[6px]">
            <label className="font-body text-xs leading-4 tracking-[1.2px] uppercase text-[#44474D]">
              Gender
            </label>
            <select
              value={formData.gender}
              onChange={(e) => setFormData({ ...formData, gender: e.target.value })}
              className="w-full bg-white px-4 py-[13px] font-body text-sm leading-[17px] text-[#191C1E] outline-none transition-all focus:ring-1 focus:ring-[#E9C176] cursor-pointer"
              style={{ boxShadow: '0px 0px 0px 1px rgba(197, 198, 205, 0.2)' }}
            >
              <option value="Male">Male</option>
              <option value="Female">Female</option>
              <option value="Other">Other</option>
            </select>
          </div>

          <div className="flex flex-col gap-[6px]">
            <label className="font-body text-xs leading-4 tracking-[1.2px] uppercase text-[#44474D]">
              Date of Birth
            </label>
            <input
              type="date"
              required
              value={formData.dob}
              onChange={(e) => setFormData({ ...formData, dob: e.target.value })}
              className="w-full bg-white px-4 py-[11px] font-body text-sm leading-[17px] text-[#191C1E] outline-none transition-all focus:ring-1 focus:ring-[#E9C176]"
              style={{ boxShadow: '0px 0px 0px 1px rgba(197, 198, 205, 0.2)' }}
            />
          </div>
        </div>

        {/* Actions */}
        <div className="flex flex-col gap-4 pt-4">
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-[#0D1C32] text-white py-4 font-body font-semibold text-base leading-6 tracking-[0.4px] text-center shadow-[0_1px_2px_rgba(0,0,0,0.05)] hover:opacity-90 active:scale-[0.99] transition-all disabled:opacity-50"
          >
            {loading ? 'Registering Account...' : 'Create Account'}
          </button>

          <div className="flex items-center justify-center py-2">
            <div className="flex-1 h-[1px]" style={{ borderTop: '1px solid rgba(197, 198, 205, 0.2)' }}></div>
            <span className="px-4 font-body font-semibold text-xs leading-4 tracking-[1.2px] uppercase text-[#44474D]">
              or
            </span>
            <div className="flex-1 h-[1px]" style={{ borderTop: '1px solid rgba(197, 198, 205, 0.2)' }}></div>
          </div>

          <GoogleAuthButton text="Continue with Google" />
        </div>

        <div className="flex items-center justify-center gap-1 mt-2">
          <span className="font-body text-sm leading-5 text-[#44474D]">
            Already have an account?
          </span>
          <Link to="/login" className="font-body font-semibold text-sm leading-5 text-[#0D1C32] hover:opacity-80 transition-opacity">
            Login
          </Link>
        </div>
      </form>
    </div>
  );
};

export default SignupForm;
