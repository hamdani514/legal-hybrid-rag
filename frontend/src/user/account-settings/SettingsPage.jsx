import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { apiFetch, clearToken } from '../../lib/api';
import { startCheckout, paymentStatus } from '../lib/payments';
import DeactivateModal from '../components/DeactivateModal';
import DeleteAccountModal from '../components/DeleteAccountModal';
import SiteNav from '../components/bound/SiteNav';
import SiteFoot from '../components/bound/SiteFoot';

const SettingsPage = () => {
  const navigate = useNavigate();

  // Active sub-section tab: 'profile' or 'subscription'
  const [activeSection, setActiveSection] = useState('profile');

  // Loading & notification states
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [upgrading, setUpgrading] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState('');
  const [saveError, setSaveError] = useState('');
  const [avatarUploading, setAvatarUploading] = useState(false);

  // Modals
  const [deactivateModalOpen, setDeactivateModalOpen] = useState(false);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);

  // Profile data
  const [profile, setProfile] = useState({
    id: '',
    name: '',
    username: '',
    email: '',
    phone_no: '',
    org: '',
    dob: '',
    gender: 'Male',
    status: 'Active',
    plan: 'Free',
    avatar_url: '',
    created_at: '',
    plan_activated_at: '',
    subscription_history: [],
  });

  // Fetch full profile and subscription information
  useEffect(() => {
    let isMounted = true;

    // Fast initial fill from localStorage
    try {
      const stored = JSON.parse(localStorage.getItem('currentUser') || 'null');
      if (stored) {
        setProfile((prev) => ({
          ...prev,
          id: stored.id || '',
          name: stored.name || '',
          username: stored.username || '',
          email: stored.email || '',
          plan: stored.plan || 'Free',
          status: stored.status || 'Active',
          avatar_url: stored.avatar_url || '',
          org: stored.org || '',
          phone_no: stored.phone_no || '',
          dob: stored.dob || '',
          gender: stored.gender || 'Male',
        }));
      }
    } catch {
      /* ignore */
    }

    const fetchProfileData = async () => {
      try {
        const storedUser = JSON.parse(localStorage.getItem('currentUser') || 'null');
        const userIdParam = storedUser?.id || storedUser?.email || '';

        const res = await apiFetch(`/api/auth/profile${userIdParam ? `?user_id=${encodeURIComponent(userIdParam)}` : ''}`);
        if (res.ok) {
          const data = await res.json();
          if (isMounted) {
            setProfile(data);
            // Sync localStorage
            try {
              const currentStored = JSON.parse(localStorage.getItem('currentUser') || '{}');
              localStorage.setItem('currentUser', JSON.stringify({ ...currentStored, ...data }));
            } catch {
              /* ignore */
            }
          }
        }
      } catch (err) {
        console.error('Error fetching user profile:', err);
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    fetchProfileData();

    return () => {
      isMounted = false;
    };
  }, []);

  const handleProfileSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setSaveSuccess('');
    setSaveError('');

    try {
      const res = await apiFetch('/api/auth/profile', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: profile.name,
          username: profile.username,
          phone_no: profile.phone_no,
          org: profile.org,
          dob: profile.dob,
          gender: profile.gender,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        setSaveError(data.detail || data.message || 'Failed to update profile.');
      } else {
        setSaveSuccess('Your profile details have been successfully updated.');
        if (data.user) {
          setProfile((prev) => ({ ...prev, ...data.user }));
          try {
            const currentStored = JSON.parse(localStorage.getItem('currentUser') || '{}');
            localStorage.setItem('currentUser', JSON.stringify({ ...currentStored, ...data.user }));
          } catch {
            /* ignore */
          }
        }
      }
    } catch (err) {
      console.error('Error saving profile:', err);
      setSaveError('Failed to communicate with the server.');
    } finally {
      setSaving(false);
    }
  };

  const handleAvatarUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.type.startsWith('image/')) {
      setSaveError('Please select a valid image file (PNG, JPG, WEBP, GIF).');
      return;
    }

    if (file.size > 10 * 1024 * 1024) {
      setSaveError('Image file size must be less than 10MB.');
      return;
    }

    setAvatarUploading(true);
    setSaveError('');
    setSaveSuccess('');

    try {
      const formData = new FormData();
      formData.append('file', file);

      const storedUser = JSON.parse(localStorage.getItem('currentUser') || 'null');
      const userIdParam = storedUser?.id || storedUser?.email || profile?.id || profile?.email || '';

      const res = await apiFetch(`/api/auth/profile/avatar${userIdParam ? `?user_id=${encodeURIComponent(userIdParam)}` : ''}`, {
        method: 'POST',
        body: formData,
      });

      const data = await res.json();
      if (!res.ok) {
        setSaveError(data.detail || data.message || 'Failed to upload profile picture to Google Drive.');
      } else {
        const newAvatarUrl = `${data.avatar_url}?t=${Date.now()}`;
        setProfile((prev) => ({ ...prev, avatar_url: newAvatarUrl }));
        setSaveSuccess('Profile picture uploaded and synced to Google Drive.');

        try {
          const currentStored = JSON.parse(localStorage.getItem('currentUser') || '{}');
          localStorage.setItem('currentUser', JSON.stringify({
            ...currentStored,
            avatar_url: newAvatarUrl,
            avatar_file_id: data.avatar_file_id,
          }));
          window.dispatchEvent(new Event('user-profile-updated'));
        } catch {
          /* ignore */
        }
      }
    } catch (err) {
      console.error('Error uploading avatar:', err);
      setSaveError('Could not upload profile picture. Please try again.');
    } finally {
      setAvatarUploading(false);
      e.target.value = '';
    }
  };

  const handleAvatarDelete = async () => {
    if (!window.confirm('Are you sure you want to remove your profile picture? This will delete it from Google Drive.')) {
      return;
    }

    setAvatarUploading(true);
    setSaveError('');
    setSaveSuccess('');

    try {
      const storedUser = JSON.parse(localStorage.getItem('currentUser') || 'null');
      const userIdParam = storedUser?.id || storedUser?.email || profile?.id || profile?.email || '';

      const res = await apiFetch(`/api/auth/profile/avatar${userIdParam ? `?user_id=${encodeURIComponent(userIdParam)}` : ''}`, {
        method: 'DELETE',
      });

      const data = await res.json();
      if (!res.ok) {
        setSaveError(data.detail || data.message || 'Failed to remove profile picture.');
      } else {
        setProfile((prev) => ({ ...prev, avatar_url: null }));
        setSaveSuccess('Profile picture removed from Google Drive. Default avatar restored.');

        try {
          const currentStored = JSON.parse(localStorage.getItem('currentUser') || '{}');
          localStorage.setItem('currentUser', JSON.stringify({
            ...currentStored,
            avatar_url: null,
            avatar_file_id: null,
          }));
          window.dispatchEvent(new Event('user-profile-updated'));
        } catch {
          /* ignore */
        }
      }
    } catch (err) {
      console.error('Error deleting avatar:', err);
      setSaveError('Could not remove profile picture.');
    } finally {
      setAvatarUploading(false);
    }
  };

  const handleUpgradeToStandard = async () => {
    setUpgrading(true);
    setSaveError('');
    try {
      const result = await startCheckout();
      if (!result?.ok) {
        setSaveError(result?.message || 'Could not initiate checkout session.');
        setUpgrading(false);
      }
      // If ok: startCheckout handles window.location.assign(url) to Stripe
    } catch (err) {
      console.error('Upgrade checkout error:', err);
      setSaveError('Failed to initiate checkout.');
      setUpgrading(false);
    }
  };

  const handleLogout = () => {
    clearToken();
    try {
      localStorage.removeItem('currentUser');
    } catch {}
    navigate('/');
  };

  // Helper date formatter
  const formatDate = (isoString) => {
    if (!isoString) return 'Ongoing';
    try {
      const d = new Date(isoString);
      if (isNaN(d.getTime())) return isoString;
      return d.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      });
    } catch {
      return isoString;
    }
  };

  const isPaid = (profile.plan || '').toLowerCase() === 'standard' || (profile.plan || '').toLowerCase() === 'advocate';

  return (
    <div className="min-h-screen bg-[#F8F9FA] text-ash-900 flex flex-col font-ui selection:bg-brand-500 selection:text-white">
      {/* Standard Full-Site Navigation Bar */}
      <SiteNav />

      {/* Main Content Container with spacing below fixed SiteNav */}
      <main className="flex-1 max-w-6xl w-full mx-auto px-6 pt-28 sm:pt-32 pb-16 flex flex-col gap-8">
        {/* Breadcrumb Navigation & Back Link */}
        <div className="flex items-center justify-between pb-1">
          <nav aria-label="Breadcrumb">
            <ol className="flex items-center gap-2 font-prose text-[13px] text-ash-500">
              <li>
                <Link to="/" className="transition-colors hover:text-brand-700">
                  Home
                </Link>
              </li>
              <li aria-hidden="true">/</li>
              <li className="font-semibold text-ash-800">Account Settings</li>
            </ol>
          </nav>

          <Link
            to="/welcome"
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-semibold text-brand-700 bg-brand-50 hover:bg-brand-100 transition-colors shadow-xs"
          >
            <span className="material-symbols-outlined text-[16px]">arrow_back</span>
            <span>Back to Research</span>
          </Link>
        </div>
        {/* Profile Card Header Banner */}
        <div className="bg-white rounded-3xl p-6 sm:p-8 border border-ash-200/80 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-6 relative overflow-hidden">
          <div className="flex items-center gap-5">
            <div className="relative shrink-0 group">
              <img
                src={profile.avatar_url || '/assets/user.png'}
                alt="User Profile"
                onError={(e) => { e.currentTarget.src = '/assets/user.png'; }}
                className="w-20 h-20 rounded-full border-3 border-brand-400/80 object-cover shadow-md bg-white"
              />
              <span
                className="absolute bottom-1 right-1 w-4 h-4 rounded-full bg-emerald-500 ring-2 ring-white"
                title="Account Active"
              />
              {/* Quick camera hover overlay */}
              <label
                htmlFor="avatar-file-input"
                className="absolute inset-0 rounded-full bg-ash-950/40 opacity-0 group-hover:opacity-100 flex items-center justify-center cursor-pointer transition-opacity backdrop-blur-[1px] text-white"
                title="Change Profile Picture"
              >
                <span className="material-symbols-outlined text-[24px]">photo_camera</span>
              </label>
            </div>

            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-3 flex-wrap">
                <h1 className="font-display font-bold text-2xl text-ash-900">
                  {profile.name || profile.username || 'Legal Counsel'}
                </h1>
                <span
                  className={`px-3 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider ${
                    isPaid
                      ? 'bg-amber-100 text-amber-800 border border-amber-300'
                      : 'bg-brand-50 text-brand-700 border border-brand-200'
                  }`}
                >
                  {profile.plan || 'Free'} Tier
                </span>
                <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                  {profile.status || 'Active'}
                </span>
              </div>
              <p className="font-prose text-sm text-ash-500">
                {profile.email || 'user@example.com'} • {profile.org || 'Chambers of Legal Practice'}
              </p>

              {/* Avatar management controls */}
              <div className="flex items-center gap-2 mt-2 flex-wrap">
                <label
                  htmlFor="avatar-file-input"
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold cursor-pointer transition-all shadow-xs ${
                    avatarUploading
                      ? 'bg-ash-100 text-ash-400 cursor-wait'
                      : 'bg-brand-50 text-brand-700 hover:bg-brand-100 border border-brand-200 active:scale-95'
                  }`}
                >
                  <span className="material-symbols-outlined text-[16px]">
                    {avatarUploading ? 'hourglass_top' : 'cloud_upload'}
                  </span>
                  <span>
                    {avatarUploading
                      ? 'Syncing with Drive...'
                      : profile.avatar_url
                      ? 'Change Photo'
                      : 'Upload Photo'}
                  </span>
                </label>
                <input
                  id="avatar-file-input"
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/gif"
                  className="hidden"
                  disabled={avatarUploading}
                  onChange={handleAvatarUpload}
                />

                {profile.avatar_url && (
                  <button
                    type="button"
                    onClick={handleAvatarDelete}
                    disabled={avatarUploading}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold text-rose-600 bg-rose-50 hover:bg-rose-100 border border-rose-200 transition-all shadow-xs active:scale-95"
                    title="Remove custom picture from Google Drive and restore default"
                  >
                    <span className="material-symbols-outlined text-[16px]">delete</span>
                    <span>Remove Photo</span>
                  </button>
                )}

                <span className="inline-flex items-center gap-1 text-[11px] text-ash-400 font-medium ml-1">
                  <span className="material-symbols-outlined text-[14px] text-brand-500">add_to_drive</span>
                  Saved to Google Drive
                </span>
              </div>

              <p className="font-mono text-xs text-ash-400 mt-0.5">
                ID: {profile.id || 'USr-1001'} {profile.created_at ? `• Member since ${formatDate(profile.created_at)}` : ''}
              </p>
            </div>
          </div>

          {/* Quick CTA or status summary */}
          <div className="flex md:flex-col items-end justify-between md:justify-center gap-2 border-t md:border-t-0 md:border-l border-ash-200 pt-4 md:pt-0 md:pl-8">
            <div className="text-left md:text-right">
              <span className="text-xs uppercase tracking-wider text-ash-400 font-bold block">
                Subscription Plan
              </span>
              <span className="font-display text-lg font-bold text-ash-900">
                {isPaid ? '$10.00 / month' : 'Free Forever'}
              </span>
            </div>
            {!isPaid && (
              <button
                onClick={() => {
                  setActiveSection('subscription');
                  handleUpgradeToStandard();
                }}
                disabled={upgrading}
                className="grad-btn text-white text-xs font-bold px-4 py-2 rounded-xl shadow-glow hover:shadow-glow-lg transition-all"
              >
                {upgrading ? 'Connecting Stripe...' : 'Upgrade Plan'}
              </button>
            )}
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="flex items-center gap-2 border-b border-ash-200 pb-px">
          <button
            onClick={() => setActiveSection('profile')}
            className={`flex items-center gap-2.5 px-6 py-3.5 font-ui text-sm font-semibold rounded-t-2xl transition-all border-b-2 ${
              activeSection === 'profile'
                ? 'border-brand-600 text-brand-700 bg-white shadow-sm'
                : 'border-transparent text-ash-500 hover:text-ash-900 hover:bg-ash-100/60'
            }`}
          >
            <span className="material-symbols-outlined text-[19px]">account_circle</span>
            <span>Profile & Account Info</span>
          </button>

          <button
            onClick={() => setActiveSection('subscription')}
            className={`flex items-center gap-2.5 px-6 py-3.5 font-ui text-sm font-semibold rounded-t-2xl transition-all border-b-2 ${
              activeSection === 'subscription'
                ? 'border-brand-600 text-brand-700 bg-white shadow-sm'
                : 'border-transparent text-ash-500 hover:text-ash-900 hover:bg-ash-100/60'
            }`}
          >
            <span className="material-symbols-outlined text-[19px]">credit_card</span>
            <span>Subscription & History</span>
            {isPaid && (
              <span className="w-2 h-2 rounded-full bg-amber-500 ml-1" />
            )}
          </button>
        </div>

        {/* Feedback alerts */}
        {saveSuccess && (
          <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 p-4 rounded-2xl text-xs font-prose flex items-center gap-2 animate-[fadeIn_0.2s_ease-out]">
            <span className="material-symbols-outlined text-sm shrink-0">check_circle</span>
            <span>{saveSuccess}</span>
          </div>
        )}

        {saveError && (
          <div className="bg-rose-50 border border-rose-200 text-rose-700 p-4 rounded-2xl text-xs font-prose flex items-center gap-2 animate-[fadeIn_0.2s_ease-out]">
            <span className="material-symbols-outlined text-sm shrink-0">error</span>
            <span>{saveError}</span>
          </div>
        )}

        {/* SECTION 1: USER PROFILE & INFORMATION */}
        {activeSection === 'profile' && (
          <div className="flex flex-col gap-8 animate-[fadeIn_0.2s_ease-out]">
            {/* User Info Form */}
            <div className="bg-white rounded-3xl p-8 border border-ash-200/80 shadow-sm flex flex-col gap-6">
              <div className="border-b border-ash-100 pb-4">
                <h2 className="font-display font-bold text-xl text-ash-900">
                  Personal Information
                </h2>
                <p className="font-prose text-xs text-ash-500 mt-1">
                  Update your contact identity and organizational details registered on VerdictAI.
                </p>
              </div>

              <form onSubmit={handleProfileSubmit} className="flex flex-col gap-6 font-prose text-sm">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* Full Name */}
                  <div className="flex flex-col gap-2">
                    <label className="text-xs font-bold text-ash-600 uppercase tracking-wider">
                      Full Name
                    </label>
                    <input
                      type="text"
                      required
                      value={profile.name}
                      onChange={(e) => setProfile({ ...profile, name: e.target.value })}
                      placeholder="e.g. Barrister Ayesha Khan"
                      className="px-4 py-3 rounded-xl border border-ash-200 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 outline-none transition-all text-ash-900 bg-ash-50/50 focus:bg-white"
                    />
                  </div>

                  {/* Username */}
                  <div className="flex flex-col gap-2">
                    <label className="text-xs font-bold text-ash-600 uppercase tracking-wider">
                      Username
                    </label>
                    <input
                      type="text"
                      required
                      value={profile.username}
                      onChange={(e) => setProfile({ ...profile, username: e.target.value })}
                      placeholder="e.g. ayesha_khan"
                      className="px-4 py-3 rounded-xl border border-ash-200 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 outline-none transition-all text-ash-900 bg-ash-50/50 focus:bg-white"
                    />
                  </div>

                  {/* Email ID (Read-only for security) */}
                  <div className="flex flex-col gap-2">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-bold text-ash-600 uppercase tracking-wider">
                        Email Address
                      </label>
                      <span className="text-[11px] font-semibold text-emerald-600 flex items-center gap-0.5">
                        <span className="material-symbols-outlined text-[13px]">verified</span>
                        Verified
                      </span>
                    </div>
                    <input
                      type="email"
                      readOnly
                      value={profile.email}
                      className="px-4 py-3 rounded-xl border border-ash-200 bg-ash-100 text-ash-600 cursor-not-allowed outline-none select-all"
                    />
                  </div>

                  {/* Organization / Chamber */}
                  <div className="flex flex-col gap-2">
                    <label className="text-xs font-bold text-ash-600 uppercase tracking-wider">
                      Chamber / Law Firm / Court
                    </label>
                    <input
                      type="text"
                      value={profile.org}
                      onChange={(e) => setProfile({ ...profile, org: e.target.value })}
                      placeholder="e.g. Supreme Court Bar Association"
                      className="px-4 py-3 rounded-xl border border-ash-200 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 outline-none transition-all text-ash-900 bg-ash-50/50 focus:bg-white"
                    />
                  </div>

                  {/* Phone Number */}
                  <div className="flex flex-col gap-2">
                    <label className="text-xs font-bold text-ash-600 uppercase tracking-wider">
                      Contact Phone
                    </label>
                    <input
                      type="tel"
                      value={profile.phone_no}
                      onChange={(e) => setProfile({ ...profile, phone_no: e.target.value })}
                      placeholder="e.g. +92 300 1234567"
                      className="px-4 py-3 rounded-xl border border-ash-200 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 outline-none transition-all text-ash-900 bg-ash-50/50 focus:bg-white"
                    />
                  </div>

                  {/* Date of Birth */}
                  <div className="flex flex-col gap-2">
                    <label className="text-xs font-bold text-ash-600 uppercase tracking-wider">
                      Date of Birth
                    </label>
                    <input
                      type="date"
                      value={profile.dob}
                      onChange={(e) => setProfile({ ...profile, dob: e.target.value })}
                      className="px-4 py-3 rounded-xl border border-ash-200 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 outline-none transition-all text-ash-900 bg-ash-50/50 focus:bg-white"
                    />
                  </div>
                </div>

                <div className="flex items-center justify-end pt-4 border-t border-ash-100">
                  <button
                    type="submit"
                    disabled={saving}
                    className="grad-btn text-white px-7 py-3 rounded-xl font-ui font-bold text-sm shadow-glow hover:shadow-glow-lg transition-all disabled:opacity-50 flex items-center gap-2"
                  >
                    {saving && (
                      <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    )}
                    <span>{saving ? 'Saving Changes...' : 'Save Profile Changes'}</span>
                  </button>
                </div>
              </form>
            </div>

            {/* Account Lifecycle & Security (Deactivate / Delete) */}
            <div className="bg-white rounded-3xl p-8 border border-rose-200/80 shadow-sm flex flex-col gap-6">
              <div className="border-b border-rose-100 pb-4">
                <h2 className="font-display font-bold text-xl text-rose-700 flex items-center gap-2">
                  <span className="material-symbols-outlined text-[22px]">security</span>
                  Account Security & Lifecycle
                </h2>
                <p className="font-prose text-xs text-ash-500 mt-1">
                  Manage temporary deactivation or permanent account termination.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Deactivate Option */}
                <div className="rounded-2xl border border-amber-200 bg-amber-50/40 p-5 flex flex-col justify-between gap-4">
                  <div>
                    <h3 className="font-display font-bold text-base text-amber-900 flex items-center gap-2">
                      <span className="material-symbols-outlined text-amber-700 text-[20px]">power_settings_new</span>
                      Deactivate Account
                    </h3>
                    <p className="font-prose text-xs text-amber-800/80 mt-1.5 leading-relaxed">
                      Temporarily freeze your legal workspace. You can restore your account, research queries, and cases anytime within 30 days via an automated reactivation email.
                    </p>
                  </div>
                  <div>
                    <button
                      type="button"
                      onClick={() => setDeactivateModalOpen(true)}
                      className="w-full sm:w-auto px-5 py-2.5 rounded-xl border border-amber-300 bg-white font-ui text-xs font-bold text-amber-800 hover:bg-amber-100 transition-colors shadow-sm"
                    >
                      Deactivate Account
                    </button>
                  </div>
                </div>

                {/* Delete Option */}
                <div className="rounded-2xl border border-rose-200 bg-rose-50/40 p-5 flex flex-col justify-between gap-4">
                  <div>
                    <h3 className="font-display font-bold text-base text-rose-900 flex items-center gap-2">
                      <span className="material-symbols-outlined text-rose-700 text-[20px]">delete_forever</span>
                      Delete Account
                    </h3>
                    <p className="font-prose text-xs text-rose-800/80 mt-1.5 leading-relaxed">
                      Permanently wipe all credentials, research history, and saved citation bookmarks from the system. This action cannot be reversed.
                    </p>
                  </div>
                  <div>
                    <button
                      type="button"
                      onClick={() => setDeleteModalOpen(true)}
                      className="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-rose-600 font-ui text-xs font-bold text-white hover:bg-rose-700 transition-colors shadow-sm"
                    >
                      Delete Account Permanently
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* SECTION 2: SUBSCRIPTION & HISTORY */}
        {activeSection === 'subscription' && (
          <div className="flex flex-col gap-8 animate-[fadeIn_0.2s_ease-out]">
            {/* Active Subscription Overview Card */}
            <div className="bg-white rounded-3xl p-8 border border-ash-200/80 shadow-sm flex flex-col gap-6">
              <div className="border-b border-ash-100 pb-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                  <h2 className="font-display font-bold text-xl text-ash-900 flex items-center gap-2">
                    <span className="material-symbols-outlined text-brand-600">verified</span>
                    Current Active Subscription
                  </h2>
                  <p className="font-prose text-xs text-ash-500 mt-1">
                    Your real-time tier entitlement and access quotas for Supreme Court precedents.
                  </p>
                </div>

                <span
                  className={`self-start sm:self-auto px-3.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider ${
                    isPaid
                      ? 'bg-amber-100 text-amber-900 border border-amber-300'
                      : 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                  }`}
                >
                  ● Active Status
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {/* Plan Tier Highlight */}
                <div className="bg-gradient-to-br from-ash-900 to-ash-950 text-white rounded-2xl p-6 flex flex-col justify-between shadow-md">
                  <div>
                    <span className="text-xs uppercase tracking-wider text-cyan-300 font-semibold">
                      Current Tier
                    </span>
                    <h3 className="font-display text-2xl font-bold mt-1">
                      {profile.plan || 'Free'} Plan
                    </h3>
                    <p className="font-prose text-xs text-ash-300 mt-2 leading-relaxed">
                      {isPaid
                        ? 'Full practitioner access with unlimited reasoning and comparative search.'
                        : 'Essential moot and academic research with 25 monthly queries.'}
                    </p>
                  </div>

                  <div className="pt-6 border-t border-white/10 mt-6 flex items-baseline justify-between">
                    <span className="font-display text-2xl font-extrabold text-white">
                      {isPaid ? '$10.00' : '$0.00'}
                    </span>
                    <span className="text-xs text-ash-400">
                      {isPaid ? '/ billed monthly' : 'no card needed'}
                    </span>
                  </div>
                </div>

                {/* Quotas & Features */}
                <div className="md:col-span-2 rounded-2xl border border-ash-200 bg-ash-50/50 p-6 flex flex-col justify-between gap-6">
                  <div>
                    <h4 className="font-ui font-bold text-xs uppercase tracking-wider text-ash-600 mb-3">
                      Included Capabilities in your tier:
                    </h4>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs font-prose text-ash-700">
                      <div className="flex items-center gap-2">
                        <span className="material-symbols-outlined text-emerald-600 text-[18px]">check_circle</span>
                        <span>{isPaid ? 'Unlimited research queries' : '25 research queries monthly'}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="material-symbols-outlined text-emerald-600 text-[18px]">check_circle</span>
                        <span>Full judgment text indexing</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="material-symbols-outlined text-emerald-600 text-[18px]">check_circle</span>
                        <span>Division & bench filtering</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="material-symbols-outlined text-emerald-600 text-[18px]">check_circle</span>
                        <span>Precision citation export</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="material-symbols-outlined text-emerald-600 text-[18px]">check_circle</span>
                        <span>{isPaid ? 'Priority retrieval queue' : 'Standard retrieval queue'}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="material-symbols-outlined text-emerald-600 text-[18px]">check_circle</span>
                        <span>{isPaid ? 'Next-business-day support' : 'Community helpdesk'}</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between border-t border-ash-200/80 pt-4">
                    <div className="text-xs text-ash-500">
                      {profile.plan_activated_at
                        ? `Activated on ${formatDate(profile.plan_activated_at)}`
                        : `Account activated on ${formatDate(profile.created_at)}`}
                    </div>
                    {!isPaid ? (
                      <button
                        type="button"
                        onClick={handleUpgradeToStandard}
                        disabled={upgrading}
                        className="grad-btn text-white px-5 py-2.5 rounded-xl text-xs font-bold shadow-glow hover:shadow-glow-lg transition-all"
                      >
                        {upgrading ? 'Connecting Stripe...' : 'Upgrade to Standard ($10/mo)'}
                      </button>
                    ) : (
                      <span className="text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-3 py-1 rounded-lg">
                        Active Paid Member
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Subscription History Section */}
            <div className="bg-white rounded-3xl p-8 border border-ash-200/80 shadow-sm flex flex-col gap-6">
              <div className="border-b border-ash-100 pb-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                  <h2 className="font-display font-bold text-xl text-ash-900 flex items-center gap-2">
                    <span className="material-symbols-outlined text-brand-600">history</span>
                    Subscription & Billing History
                  </h2>
                  <p className="font-prose text-xs text-ash-500 mt-1">
                    Complete archival record of your historical subscriptions, purchases, and billing periods.
                  </p>
                </div>
                <div className="text-xs font-mono text-ash-400">
                  {profile.subscription_history?.length || 1} Record(s) logged
                </div>
              </div>

              {/* History Table */}
              <div className="overflow-x-auto rounded-2xl border border-ash-200">
                <table className="w-full text-left font-ui text-xs">
                  <thead className="bg-ash-50 border-b border-ash-200 text-ash-600 font-bold uppercase tracking-wider text-[11px]">
                    <tr>
                      <th className="py-3.5 px-4">Subscription Plan</th>
                      <th className="py-3.5 px-4">Start / Buy Date</th>
                      <th className="py-3.5 px-4">End / Expiry Date</th>
                      <th className="py-3.5 px-4">Amount Billed</th>
                      <th className="py-3.5 px-4">Payment Method</th>
                      <th className="py-3.5 px-4 text-center">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-ash-200 bg-white">
                    {profile.subscription_history && profile.subscription_history.length > 0 ? (
                      profile.subscription_history.map((record, idx) => (
                        <tr key={record.id || idx} className="hover:bg-ash-50/60 transition-colors">
                          <td className="py-4 px-4 font-semibold text-ash-900">
                            <div className="flex items-center gap-2">
                              <span className="w-2 h-2 rounded-full bg-brand-500" />
                              <span>{record.tier_name || `${record.plan} Plan`}</span>
                            </div>
                          </td>
                          <td className="py-4 px-4 text-ash-600 font-prose">
                            {formatDate(record.started_at)}
                          </td>
                          <td className="py-4 px-4 text-ash-600 font-prose">
                            {record.ended_at ? formatDate(record.ended_at) : (
                              <span className="text-emerald-700 font-medium">Ongoing (Active)</span>
                            )}
                          </td>
                          <td className="py-4 px-4 font-mono font-medium text-ash-800">
                            {record.amount || (record.plan === 'Standard' ? '$10.00 / mo' : '$0.00')}
                          </td>
                          <td className="py-4 px-4 text-ash-600">
                            <span className="inline-flex items-center gap-1.5">
                              <span className="material-symbols-outlined text-[15px] text-ash-400">credit_card</span>
                              {record.payment_method || 'System Provision'}
                            </span>
                          </td>
                          <td className="py-4 px-4 text-center">
                            <span
                              className={`inline-block px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                                record.status?.toLowerCase() === 'active'
                                  ? 'bg-emerald-100 text-emerald-800 border border-emerald-200'
                                  : record.status?.toLowerCase() === 'completed'
                                  ? 'bg-sky-100 text-sky-800 border border-sky-200'
                                  : 'bg-ash-100 text-ash-600 border border-ash-200'
                              }`}
                            >
                              {record.status || 'Active'}
                            </span>
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan="6" className="py-8 text-center text-ash-500 font-prose">
                          No previous subscription transactions found.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>

              {/* Security & Invoicing Note */}
              <div className="bg-ash-50 rounded-2xl p-4 border border-ash-200/80 flex items-start gap-3 text-xs text-ash-600 font-prose leading-relaxed">
                <span className="material-symbols-outlined text-brand-600 text-[18px] shrink-0 mt-0.5">lock</span>
                <span>
                  All payments and checkout invoices are securely authenticated and processed by Stripe with 256-bit encryption. You can cancel active subscriptions at any time with no lock-in.
                </span>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Deactivate Account Modal */}
      <DeactivateModal
        isOpen={deactivateModalOpen}
        onClose={() => setDeactivateModalOpen(false)}
        userEmail={profile.email}
      />

      {/* Delete Account Modal */}
      <DeleteAccountModal
        isOpen={deleteModalOpen}
        onClose={() => setDeleteModalOpen(false)}
        userEmail={profile.email}
      />

      {/* Footer */}
      <SiteFoot />
    </div>
  );
};

export default SettingsPage;
