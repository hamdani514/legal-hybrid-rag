import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

/**
 * Administrator sign-in. The form only — AuthShell supplies the split layout
 * and the visual panel, so this no longer carries its own branding column.
 *
 * The authentication contract is unchanged: POST /api/admin/login, the
 * response stored as `currentAdmin`, then on to the dashboard.
 */
const AdminLoginForm = () => {
  const [showPassword, setShowPassword] = useState(false);
  const [adminid, setAdminid] = useState('');
  const [password, setPassword] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setLoading(true);

    try {
      const res = await fetch('/api/admin/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ adminid, password }),
      });

      if (res.ok) {
        const data = await res.json();
        localStorage.setItem('currentAdmin', JSON.stringify(data));
        navigate('/admin/dashboard');
      } else {
        const data = await res.json();
        setErrorMsg(data?.detail || 'Invalid Admin ID or Password.');
      }
    } catch (error) {
      console.error('Login error:', error);
      setErrorMsg('Failed to connect to the authentication server.');
    } finally {
      setLoading(false);
    }
  };

  const fieldClass =
    'w-full rounded-xl border border-ash-200 bg-white py-3.5 pl-11 font-prose text-[15px] leading-6 text-ash-900 placeholder:text-ash-400 outline-none transition-all duration-250 focus:border-brand-400 focus:ring-4 focus:ring-brand-500/12';

  return (
    <div className="pop-in flex w-full flex-col">
      {/* Header — states plainly that this is the console, not the app. */}
      <span className="inline-flex w-fit items-center gap-2 rounded-full border border-brand-100 bg-brand-50 px-3.5 py-1.5 font-ui text-[11.5px] font-semibold text-brand-700">
        <span aria-hidden="true" className="material-symbols-outlined text-[15px]">
          shield_person
        </span>
        Administration
      </span>

      <h1 className="mt-6 font-display text-[1.875rem] font-bold leading-[1.15] tracking-[-0.025em] text-ash-900">
        Console sign-in
      </h1>
      <p className="mt-2.5 font-prose text-[14.5px] leading-6 text-ash-600">
        Enter your administrator credentials to manage the archive.
      </p>

      {errorMsg && (
        <div
          role="alert"
          className="mt-7 flex items-start gap-2.5 rounded-2xl border border-red-200 bg-red-50 p-4 font-prose text-[13px] text-red-700"
        >
          <span
            aria-hidden="true"
            className="material-symbols-outlined shrink-0 text-base leading-5"
          >
            error
          </span>
          <span>{errorMsg}</span>
        </div>
      )}

      <form className="mt-8 flex flex-col gap-5" onSubmit={handleSubmit}>
        {/* Admin ID ------------------------------------------------------ */}
        <div className="flex flex-col gap-2">
          <label
            htmlFor="admin-id"
            className="font-ui text-[11px] font-semibold uppercase tracking-[0.08em] text-ash-500"
          >
            Admin ID
          </label>
          <div className="relative w-full">
            <span
              aria-hidden="true"
              className="material-symbols-outlined absolute left-3.5 top-1/2 -translate-y-1/2 text-[18px] text-ash-400"
            >
              badge
            </span>
            <input
              id="admin-id"
              type="text"
              value={adminid}
              onChange={(e) => setAdminid(e.target.value)}
              required
              autoComplete="username"
              placeholder="admin@example.com"
              className={fieldClass}
            />
          </div>
        </div>

        {/* Password ------------------------------------------------------ */}
        <div className="flex flex-col gap-2">
          <label
            htmlFor="admin-password"
            className="font-ui text-[11px] font-semibold uppercase tracking-[0.08em] text-ash-500"
          >
            Password
          </label>
          <div className="relative w-full">
            <span
              aria-hidden="true"
              className="material-symbols-outlined absolute left-3.5 top-1/2 -translate-y-1/2 text-[18px] text-ash-400"
            >
              key
            </span>
            <input
              id="admin-password"
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              placeholder="••••••••••••"
              className={`${fieldClass} pr-12`}
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              aria-label={showPassword ? 'Hide password' : 'Show password'}
              className="absolute right-3.5 top-1/2 flex -translate-y-1/2 items-center text-ash-400 transition-colors duration-250 hover:text-ash-700"
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[19px]">
                {showPassword ? 'visibility_off' : 'visibility'}
              </span>
            </button>
          </div>
        </div>

        {/* Remember this workstation ------------------------------------- */}
        <label htmlFor="admin-remember" className="flex cursor-pointer items-center gap-2.5">
          <input
            id="admin-remember"
            type="checkbox"
            className="h-4 w-4 rounded border-ash-300 text-brand-600 focus:ring-2 focus:ring-brand-500/25 focus:ring-offset-0"
          />
          <span className="font-prose text-[13.5px] text-ash-600">Remember this workstation</span>
        </label>

        <button
          type="submit"
          disabled={loading}
          className="grad-btn group mt-2 flex w-full items-center justify-center gap-2.5 rounded-full py-4 font-ui text-[15px] font-bold text-white shadow-glow transition-all duration-300 hover:-translate-y-0.5 hover:shadow-glow-lg active:translate-y-0 disabled:cursor-not-allowed disabled:translate-y-0 disabled:opacity-60 disabled:shadow-none"
        >
          {loading ? (
            <>
              <svg className="h-4 w-4 animate-spin text-white" fill="none" viewBox="0 0 24 24">
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              Authenticating…
            </>
          ) : (
            <>
              Sign in to console
              <span
                aria-hidden="true"
                className="material-symbols-outlined text-[18px] transition-transform duration-300 group-hover:translate-x-1"
              >
                arrow_forward
              </span>
            </>
          )}
        </button>
      </form>

      {/* Notice — an admin door should say so. */}
      <div className="mt-9 flex items-start gap-2.5 rounded-2xl border border-amber-400/40 bg-amber-400/10 p-4">
        <span
          aria-hidden="true"
          className="material-symbols-outlined shrink-0 text-[18px] text-amber-500"
        >
          warning
        </span>
        <p className="font-prose text-[12.5px] leading-[1.6] text-ash-700">
          Access is restricted and monitored. Contact system oversight for new credentials.
        </p>
      </div>

      <p className="mt-7 text-center font-prose text-[13px] text-ash-500">
        Researcher rather than administrator?{' '}
        <Link to="/login" className="font-semibold text-brand-700 hover:text-brand-800">
          Sign in here
        </Link>
      </p>
    </div>
  );
};

export default AdminLoginForm;
