import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiFetch, clearToken } from '../../lib/api';

export default function DeleteAccountModal({ isOpen, onClose, userEmail }) {
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const navigate = useNavigate();

  if (!isOpen) return null;

  const handleDelete = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setSuccessMsg('');

    if (!password.trim()) {
      setErrorMsg('Please enter your password or type CONFIRM to delete.');
      return;
    }

    setLoading(true);

    try {
      const res = await apiFetch('/api/auth/delete-account', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: userEmail,
          password: password.trim(),
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        setErrorMsg(data.detail || data.message || 'Account deletion failed.');
        setLoading(false);
        return;
      }

      setSuccessMsg(data.message || 'Your account has been permanently deleted.');
      setLoading(false);

      // Sign out and redirect to home after 2 seconds
      setTimeout(() => {
        try {
          localStorage.removeItem('currentUser');
        } catch {}
        clearToken();
        navigate('/');
      }, 2000);
    } catch (err) {
      console.error('Delete account error:', err);
      setErrorMsg('Failed to communicate with authentication server.');
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-[fadeIn_0.2s_ease-out]">
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
          <div className="w-12 h-12 rounded-full bg-red-100 text-red-600 flex items-center justify-center shrink-0">
            <span className="material-symbols-outlined text-2xl">delete_forever</span>
          </div>
          <div className="flex flex-col">
            <h2 className="font-display font-bold text-xl text-red-600">
              Permanently Delete Account
            </h2>
            <p className="font-prose text-xs text-ash-500 mt-1">
              Account: <strong className="text-ash-800">{userEmail}</strong>
            </p>
          </div>
        </div>

        {/* Warning Details */}
        <div className="bg-red-50/70 border border-red-200 rounded-xl p-4 text-xs font-prose text-red-900 leading-relaxed">
          <strong className="block text-red-700 font-semibold mb-1">Warning: Irreversible Action</strong>
          Deleting your account will permanently erase your profile, saved legal conversations, and active subscription details. You will not be able to recover this data.
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
          <form onSubmit={handleDelete} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <label className="font-prose text-xs font-bold leading-4 uppercase tracking-[1.2px] text-ash-600">
                Confirm Password
              </label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  required
                  placeholder="Enter your password or CONFIRM"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={loading}
                  className="w-full bg-ash-50 border border-ash-300 rounded-xl px-4 py-3 text-sm font-prose text-ash-900 focus:outline-none focus:border-red-500 focus:bg-white transition-all pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-ash-400 hover:text-ash-600 transition-colors"
                >
                  <span className="material-symbols-outlined text-lg">
                    {showPassword ? 'visibility_off' : 'visibility'}
                  </span>
                </button>
              </div>
              <p className="text-[11px] text-ash-500">
                For Google-authenticated accounts, enter <code className="bg-ash-100 px-1 py-0.5 rounded text-ash-700 font-semibold">CONFIRM</code>.
              </p>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                disabled={loading}
                className="px-5 py-2.5 rounded-xl border border-ash-300 text-ash-700 font-ui text-xs font-semibold hover:bg-ash-50 transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading}
                className="px-6 py-2.5 rounded-xl bg-red-600 text-white font-ui text-xs font-bold hover:bg-red-700 shadow-sm transition-all flex items-center gap-1.5 disabled:opacity-50"
              >
                {loading && (
                  <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                )}
                <span>{loading ? 'Deleting...' : 'Delete Permanently'}</span>
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
