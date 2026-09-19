import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

export default function DeactivateModal({ isOpen, onClose, userEmail }) {
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const navigate = useNavigate();

  if (!isOpen) return null;

  const handleDeactivate = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setSuccessMsg('');

    if (!password.trim()) {
      setErrorMsg('Please enter your password or type CONFIRM.');
      return;
    }

    setLoading(true);

    try {
      const res = await fetch('/api/auth/deactivate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: userEmail,
          password: password.trim(),
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        setErrorMsg(data.detail || data.message || 'Deactivation failed.');
        setLoading(false);
        return;
      }

      setSuccessMsg(data.message || 'Account successfully deactivated. Check your email for reactivation details.');
      setLoading(false);

      // Sign out and redirect after 2.5 seconds
      setTimeout(() => {
        localStorage.removeItem('currentUser');
        navigate('/login');
      }, 2500);
    } catch (err) {
      console.error('Deactivation error:', err);
      setErrorMsg('Failed to communicate with authentication server.');
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4 animate-[fadeIn_0.2s_ease-out]">
      <div className="bg-white rounded-2xl border border-ash-200 shadow-2xl max-w-md w-full p-6 sm:p-8 flex flex-col gap-6 relative">
        {/* Close Button */}
        <button
          onClick={onClose}
          disabled={loading || successMsg}
          className="absolute top-5 right-5 text-ash-400 hover:text-ash-700 transition-colors"
        >
          <span className="material-symbols-outlined text-xl">close</span>
        </button>

        {/* Modal Header */}
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-full bg-rose-100 text-rose-600 flex items-center justify-center shrink-0">
            <span className="material-symbols-outlined text-2xl">warning</span>
          </div>
          <div className="flex flex-col">
            <h2 className="font-display font-bold text-xl text-ash-900">
              Deactivate Account
            </h2>
            <p className="font-prose text-xs text-ash-500 mt-1">
              Account: <strong className="text-ash-800">{userEmail}</strong>
            </p>
          </div>
        </div>

        {/* Warning Details */}
        <div className="bg-ash-50 border border-ash-200 rounded-xl p-4 text-xs font-prose text-ash-600 leading-relaxed">
          Deactivating your account immediately suspends active research sessions. You will receive a secure reactivation link via email to restore full access anytime within <strong>30 days</strong>.
        </div>

        {/* Feedback Alerts */}
        {errorMsg && (
          <div className="bg-rose-50 text-rose-700 p-3.5 rounded-xl border border-rose-200 text-xs font-prose flex items-center gap-2">
            <span className="material-symbols-outlined text-sm shrink-0">error</span>
            <span>{errorMsg}</span>
          </div>
        )}

        {successMsg && (
          <div className="bg-emerald-50 text-emerald-800 p-4 rounded-xl border border-emerald-200 text-xs font-prose flex items-center gap-2">
            <span className="material-symbols-outlined text-sm shrink-0">check_circle</span>
            <span>{successMsg}</span>
          </div>
        )}

        {/* Confirmation Form */}
        {!successMsg && (
          <form onSubmit={handleDeactivate} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <label className="font-prose text-xs font-bold leading-4 uppercase tracking-[1.2px] text-ash-600">
                Confirm Password
              </label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  required
                  placeholder="Enter password or CONFIRM"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full rounded-xl border border-ash-200 bg-white px-4 py-3 font-prose text-sm text-ash-900 placeholder:text-ash-400 outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-500/20"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-ash-400 hover:text-ash-600 transition-colors flex items-center"
                >
                  <span className="material-symbols-outlined text-lg">
                    {showPassword ? 'visibility_off' : 'visibility'}
                  </span>
                </button>
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                disabled={loading}
                className="px-5 py-2.5 rounded-xl border border-ash-200 font-ui text-xs font-semibold text-ash-700 hover:bg-ash-100 transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading}
                className="px-5 py-2.5 rounded-xl bg-rose-600 font-ui text-xs font-bold text-white shadow-sm hover:bg-rose-700 transition-all disabled:opacity-50 flex items-center gap-2"
              >
                {loading ? (
                  <>
                    <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                    Deactivating...
                  </>
                ) : (
                  'Confirm Deactivation'
                )}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
