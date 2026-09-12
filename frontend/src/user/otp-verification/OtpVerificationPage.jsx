import React from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import UserFooter from '../components/UserFooter';
import OtpVerificationStep from '../components/auth/OtpVerificationStep';

const OtpVerificationPage = () => {
  const location = useLocation();
  const navigate = useNavigate();

  // Retrieve email passed from /forgot-password or query param
  const emailFromState = location.state?.email;
  const searchParams = new URLSearchParams(location.search);
  const email = emailFromState || searchParams.get('email') || 'counselor@firm.com';

  const handleVerified = (code) => {
    // Navigate to the dedicated Reset Password screen
    navigate('/reset-password', { state: { email, code } });
  };

  const handleChangeEmail = () => {
    navigate('/forgot-password');
  };

  return (
    <div className="flex flex-col bg-[#F8F9FB] min-h-screen w-full">
      {/* Header */}
      <header className="w-full bg-[#F8F9FB] sticky top-0 z-50">
        <nav className="flex justify-between items-center w-full px-8 py-4 h-[68px]">
          <Link to="/" className="font-headline text-2xl text-[#0D1C32] tracking-[-1.2px] leading-8">
            Verdict AI
          </Link>
          <div className="flex items-center gap-4">
            <Link
              to="/forgot-password"
              className="text-xs uppercase tracking-[1.2px] font-semibold text-[#44474D] hover:text-[#0D1C32] transition-colors"
            >
              Back to Recovery
            </Link>
            <Link
              to="/"
              className="bg-[#0D1C32] text-white px-5 py-2 rounded-[2px] font-body text-xs font-semibold leading-5 tracking-[1.4px] uppercase text-center hover:opacity-90 transition-opacity"
            >
              Home
            </Link>
          </div>
        </nav>
      </header>

      {/* Main Container */}
      <main className="flex-grow flex items-center justify-center px-4 py-12 relative overflow-hidden">
        <div
          className="w-full max-w-[1024px] grid md:grid-cols-2 bg-white overflow-hidden z-10"
          style={{ boxShadow: '0px 32px 64px -12px rgba(0, 0, 0, 0.04)' }}
        >
          {/* Left Hero Pane */}
          <div className="hidden md:flex bg-[#0D1C32] relative p-12 flex-col justify-between overflow-hidden">
            <div className="flex flex-col gap-6">
              <span className="font-body text-xs uppercase tracking-[1.6px] text-[#E9C176] font-semibold">
                Multi-Factor Validation
              </span>
              <h2 className="font-headline font-normal text-[44px] leading-[54px] tracking-[-1.2px] text-white">
                Sovereign Editorial Intelligence.
              </h2>
              <p className="font-body text-base leading-[26px] text-[#76849F] max-w-[340px]">
                Confirm custody of your authorized communication channel before altering firm credentials.
              </p>
            </div>

            {/* Steps Guide */}
            <div className="flex flex-col gap-3 py-6 border-t border-b border-[#76849F]/20 my-4">
              <div className="flex items-center gap-3 text-xs font-body text-white">
                <span className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold bg-[#E9C176] text-[#0D1C32]">
                  ✓
                </span>
                <span className="text-[#76849F]">1. Request Verification Code</span>
              </div>
              <div className="flex items-center gap-3 text-xs font-body text-white">
                <span className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold bg-[#E9C176] text-[#0D1C32]">
                  2
                </span>
                <span className="font-semibold text-white">2. Multi-Factor OTP Verification</span>
              </div>
              <div className="flex items-center gap-3 text-xs font-body text-[#76849F]">
                <span className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold border border-[#76849F]/40 text-[#76849F]">
                  3
                </span>
                <span>3. Establish New Credentials</span>
              </div>
            </div>

            {/* Footer Badge */}
            <div className="flex items-center gap-4">
              <div
                className="w-11 h-11 flex items-center justify-center rounded-xl shrink-0"
                style={{ border: '1px solid rgba(118, 132, 159, 0.3)' }}
              >
                <span className="material-symbols-outlined text-[#E9C176]" style={{ fontSize: '18px' }}>
                  shield_locked
                </span>
              </div>
              <div className="flex flex-col">
                <span className="font-body font-semibold text-xs leading-4 tracking-[1.2px] uppercase text-[#FFDEA5]">
                  Hardware-Grade OTP
                </span>
                <span className="font-body text-[11px] leading-4 text-[#76849F]">
                  Zero-knowledge challenge protocol.
                </span>
              </div>
            </div>
          </div>

          {/* Right Form Pane */}
          <div className="p-8 sm:p-12 md:p-14 flex flex-col justify-center">
            <OtpVerificationStep
              email={email}
              onVerified={handleVerified}
              onChangeEmail={handleChangeEmail}
            />
          </div>
        </div>
      </main>

      <UserFooter />
    </div>
  );
};

export default OtpVerificationPage;
