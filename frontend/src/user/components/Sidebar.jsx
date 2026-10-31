import { useEffect, useRef, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { relativeTime } from '../lib/chatHistory';
import DeactivateModal from './DeactivateModal';

/*
 * The research sidebar: a new-query button, saved conversations, and user profile.
 * Supports expanded mode (w-72) and collapsed ChatGPT-style icon rail (w-[68px]).
 */
const Sidebar = ({
  onNewQuery,
  userEmail,
  sessions = [],
  activeSessionId = '',
  onOpenSession,
  onPinSession,
  onDeleteSession,
  onRenameSession,
  loading = false,
  activeTab,
  isOpen = true,
  onToggleSidebar,
  onLogout,
}) => {
  const navigate = useNavigate();
  const [menuFor, setMenuFor] = useState('');
  const [renamingId, setRenamingId] = useState('');
  const [draft, setDraft] = useState('');
  const renameRef = useRef(null);
  // True once the open rename has been saved or cancelled, so the blur that
  // follows Enter or Escape (the input leaving the page) does not act again.
  const renameDone = useRef(true);

  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const [deactivateModalOpen, setDeactivateModalOpen] = useState(false);
  const profileMenuRef = useRef(null);

  const [currentUser, setCurrentUser] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('currentUser') || 'null');
    } catch {
      return null;
    }
  });

  useEffect(() => {
    const handleProfileUpdate = () => {
      try {
        setCurrentUser(JSON.parse(localStorage.getItem('currentUser') || 'null'));
      } catch {
        setCurrentUser(null);
      }
    };
    window.addEventListener('storage', handleProfileUpdate);
    window.addEventListener('user-profile-updated', handleProfileUpdate);
    return () => {
      window.removeEventListener('storage', handleProfileUpdate);
      window.removeEventListener('user-profile-updated', handleProfileUpdate);
    };
  }, []);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (profileMenuRef.current && !profileMenuRef.current.contains(event.target)) {
        setProfileMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    if (renamingId && renameRef.current) {
      renameRef.current.focus();
      renameRef.current.select();
    }
  }, [renamingId]);

  // Escape closes whichever menu is open.
  useEffect(() => {
    if (!menuFor && !renamingId && !profileMenuOpen) return undefined;
    const onKey = (e) => {
      if (e.key !== 'Escape') return;
      setMenuFor('');
      renameDone.current = true;   // Escape cancels a rename
      setRenamingId('');
      setProfileMenuOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [menuFor, renamingId, profileMenuOpen]);

  const startRename = (s) => {
    renameDone.current = false;
    setMenuFor('');
    setDraft(s.title);
    setRenamingId(s.session_id);
  };

  const commitRename = async (s) => {
    if (renameDone.current) return;
    renameDone.current = true;
    const title = draft.trim();
    setRenamingId('');
    if (title && title !== s.title) await onRenameSession?.(s.session_id, title);
  };

  const pinned = sessions.filter((s) => s.pinned);
  const rest = sessions.filter((s) => !s.pinned);

  const initials = (() => {
    const name = currentUser?.name || currentUser?.username;
    if (name) {
      const parts = name.trim().split(/\s+/);
      if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
      return name.slice(0, 2).toUpperCase();
    }
    if (userEmail) {
      return userEmail.slice(0, 2).toUpperCase();
    }
    return 'DA';
  })();

  const renderAvatar = (size = 'w-9 h-9 text-xs') => {
    if (currentUser?.avatar_url) {
      return (
        <img
          src={currentUser.avatar_url}
          alt="Profile"
          onError={(e) => {
            e.currentTarget.style.display = 'none';
          }}
          className={`${size} rounded-full object-cover border border-ash-200 shadow-sm bg-white`}
        />
      );
    }
    return (
      <div
        className={`${size} rounded-full bg-gradient-to-tr from-amber-500 to-amber-400 text-white font-bold font-ui flex items-center justify-center shadow-sm select-none`}
      >
        {initials}
      </div>
    );
  };

  // A render function for the same reason as renderRow below.
  const renderProfilePopup = (positionClasses = 'left-0 bottom-full mb-2 w-full') => {
    const displayName =
      currentUser?.name ||
      currentUser?.username ||
      (userEmail ? userEmail.split('@')[0] : 'Legal Counsel');
    const displayEmail =
      userEmail || currentUser?.email || currentUser?.user?.email || 'Authenticated User';
    const planName = currentUser?.plan || currentUser?.user?.plan || 'STANDARD';

    return (
      <div
        className={`absolute ${positionClasses} bg-white rounded-2xl border border-ash-200/90 shadow-[0_20px_50px_rgba(15,23,42,0.2),0_0_0_1px_rgba(15,23,42,0.06)] p-2.5 flex flex-col gap-1 z-[60] animate-[fadeIn_0.15s_ease-out] select-none`}
      >
        {/* User Identity Header Card */}
        <div className="flex items-center gap-3 p-2.5 bg-gradient-to-br from-ash-50 via-white to-brand-50/50 rounded-xl border border-ash-200/70 mb-1">
          <div className="shrink-0">{renderAvatar('w-10 h-10 text-xs')}</div>
          <div className="min-w-0 flex-1">
            <p className="truncate font-ui text-[13.5px] font-bold text-ash-900 leading-tight">
              {displayName}
            </p>
            <p className="truncate font-ui text-[11px] text-ash-500 mt-0.5">{displayEmail}</p>
            <div className="mt-1.5 flex items-center">
              <span className="inline-flex items-center gap-1 rounded-full bg-brand-100 border border-brand-200/80 px-2.5 py-0.5 font-ui text-[9.5px] font-bold uppercase tracking-wider text-brand-800 shadow-xs">
                <span className="h-1.5 w-1.5 rounded-full bg-brand-500 animate-pulse" />
                {planName} Plan
              </span>
            </div>
          </div>
        </div>

        {/* Menu Actions with rich icon badges and hover states */}
        <button
          type="button"
          onClick={() => {
            setProfileMenuOpen(false);
            navigate('/settings');
          }}
          className="group flex items-center gap-2.5 rounded-xl px-2.5 py-2 text-left transition-all duration-150 hover:bg-brand-50/70 cursor-pointer"
        >
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-ash-100 text-ash-600 transition-colors group-hover:bg-brand-100 group-hover:text-brand-700">
            <span className="material-symbols-outlined text-[18px]">settings</span>
          </span>
          <span className="flex-1 font-ui text-[13px] font-semibold text-ash-800 transition-colors group-hover:text-ash-900">
            Account Settings
          </span>
          <span className="material-symbols-outlined text-[16px] text-ash-400 transition-all group-hover:translate-x-0.5 group-hover:text-brand-600">
            chevron_right
          </span>
        </button>

        <button
          type="button"
          onClick={() => {
            setProfileMenuOpen(false);
            navigate('/pricing');
          }}
          className="group flex items-center gap-2.5 rounded-xl px-2.5 py-2 text-left transition-all duration-150 hover:bg-brand-50/70 cursor-pointer"
        >
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-ash-100 text-ash-600 transition-colors group-hover:bg-brand-100 group-hover:text-brand-700">
            <span className="material-symbols-outlined text-[18px]">credit_card</span>
          </span>
          <span className="flex-1 font-ui text-[13px] font-semibold text-ash-800 transition-colors group-hover:text-ash-900">
            Plans & Billing
          </span>
          <span className="material-symbols-outlined text-[16px] text-ash-400 transition-all group-hover:translate-x-0.5 group-hover:text-brand-600">
            chevron_right
          </span>
        </button>

        <Link
          to="/terms"
          onClick={() => setProfileMenuOpen(false)}
          className="group flex items-center gap-2.5 rounded-xl px-2.5 py-2 text-left transition-all duration-150 hover:bg-brand-50/70"
        >
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-ash-100 text-ash-600 transition-colors group-hover:bg-brand-100 group-hover:text-brand-700">
            <span className="material-symbols-outlined text-[18px]">gavel</span>
          </span>
          <span className="flex-1 font-ui text-[13px] font-semibold text-ash-800 transition-colors group-hover:text-ash-900">
            Terms of Service
          </span>
          <span className="material-symbols-outlined text-[16px] text-ash-400 transition-all group-hover:translate-x-0.5 group-hover:text-brand-600">
            chevron_right
          </span>
        </Link>

        <Link
          to="/privacy"
          onClick={() => setProfileMenuOpen(false)}
          className="group flex items-center gap-2.5 rounded-xl px-2.5 py-2 text-left transition-all duration-150 hover:bg-brand-50/70"
        >
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-ash-100 text-ash-600 transition-colors group-hover:bg-brand-100 group-hover:text-brand-700">
            <span className="material-symbols-outlined text-[18px]">privacy_tip</span>
          </span>
          <span className="flex-1 font-ui text-[13px] font-semibold text-ash-800 transition-colors group-hover:text-ash-900">
            Privacy Policy
          </span>
          <span className="material-symbols-outlined text-[16px] text-ash-400 transition-all group-hover:translate-x-0.5 group-hover:text-brand-600">
            chevron_right
          </span>
        </Link>

        <div className="my-1 border-t border-ash-200/80" />

        <button
          type="button"
          onClick={() => {
            setProfileMenuOpen(false);
            setDeactivateModalOpen(true);
          }}
          className="group flex items-center gap-2.5 rounded-xl px-2.5 py-2 text-left transition-all duration-150 hover:bg-rose-50 cursor-pointer"
        >
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-rose-50 text-rose-500 transition-colors group-hover:bg-rose-100 group-hover:text-rose-600">
            <span className="material-symbols-outlined text-[17px]">power_settings_new</span>
          </span>
          <span className="flex-1 font-ui text-[12.5px] font-semibold text-rose-600 transition-colors group-hover:text-rose-700">
            Deactivate Account
          </span>
        </button>

        <button
          type="button"
          onClick={() => {
            setProfileMenuOpen(false);
            onLogout?.();
          }}
          className="group flex items-center gap-2.5 rounded-xl px-2.5 py-2 text-left transition-all duration-150 hover:bg-ash-900 cursor-pointer"
        >
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-ash-100 text-ash-700 transition-colors group-hover:bg-ash-800 group-hover:text-white">
            <span className="material-symbols-outlined text-[18px]">logout</span>
          </span>
          <span className="flex-1 font-ui text-[13px] font-bold text-ash-800 transition-colors group-hover:text-white">
            Sign Out
          </span>
          <span className="material-symbols-outlined text-[16px] text-ash-400 transition-all group-hover:translate-x-0.5 group-hover:text-white">
            chevron_right
          </span>
        </button>
      </div>
    );
  };

  // Render functions, not components: a component defined inside Sidebar is a
  // new type on every render, so React rebuilt the rename input after each
  // keystroke and it lost focus after one character.
  const renderRow = (s) => {
    const isActive = s.session_id === activeSessionId && activeTab === 'case';
    const isMenuOpen = menuFor === s.session_id;

    if (renamingId === s.session_id) {
      return (
        <li key={s.session_id}>
          <input
            ref={renameRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => commitRename(s)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitRename(s);
              if (e.key === 'Escape') {
                renameDone.current = true;
                setRenamingId('');
              }
            }}
            className="w-full rounded-lg border border-brand-500 bg-white px-3 py-2 font-prose text-[13px] text-ash-900 outline-none ring-2 ring-brand-100"
          />
        </li>
      );
    }

    return (
      <li key={s.session_id} className="group relative">
        <button
          onClick={() => onOpenSession?.(s.session_id)}
          title={`${s.title}\n${relativeTime(s.updated_at)}`}
          className={`flex w-full items-center rounded-lg py-2 pl-3 pr-9 text-left transition-colors ${
            isActive ? 'bg-white text-ash-900 shadow-soft' : 'text-ash-600 hover:bg-white/60 hover:text-ash-900'
          }`}
        >
          {s.pinned && (
            <span
              className="material-symbols-outlined mr-1.5 shrink-0 text-[13px] text-brand-600"
              style={{ fontVariationSettings: "'FILL' 1" }}
            >
              push_pin
            </span>
          )}
          <span className="truncate font-prose text-[13px] leading-5">{s.title}</span>
        </button>

        <button
          onClick={(e) => {
            e.stopPropagation();
            setMenuFor(isMenuOpen ? '' : s.session_id);
          }}
          title="More"
          className={`absolute right-1 top-1/2 -translate-y-1/2 rounded p-1 text-ash-400 transition-opacity hover:bg-ash-200/60 hover:text-ash-700 ${
            isMenuOpen ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 focus:opacity-100'
          }`}
        >
          <span className="material-symbols-outlined text-[18px]">more_horiz</span>
        </button>

        {isMenuOpen && (
          <div className="absolute right-1 top-9 z-50 w-40 overflow-hidden rounded-xl border border-ash-200 bg-white py-1 shadow-lg">
            <button
              onClick={() => startRename(s)}
              className="flex w-full items-center gap-2.5 px-3 py-2 text-left font-prose text-[13px] text-ash-700 hover:bg-ash-50"
            >
              <span className="material-symbols-outlined text-[17px]">edit</span>
              Rename
            </button>
            <button
              onClick={() => {
                setMenuFor('');
                onPinSession?.(s.session_id, !s.pinned);
              }}
              className="flex w-full items-center gap-2.5 px-3 py-2 text-left font-prose text-[13px] text-ash-700 hover:bg-ash-50"
            >
              <span className="material-symbols-outlined text-[17px]">push_pin</span>
              {s.pinned ? 'Unpin' : 'Pin'}
            </button>
            <button
              onClick={() => {
                setMenuFor('');
                onDeleteSession?.(s.session_id);
              }}
              className="flex w-full items-center gap-2.5 px-3 py-2 text-left font-prose text-[13px] text-red-600 hover:bg-red-50"
            >
              <span className="material-symbols-outlined text-[17px]">delete</span>
              Delete
            </button>
          </div>
        )}
      </li>
    );
  };

  const renderGroup = (label, rows) =>
    rows.length === 0 ? null : (
      <>
        <p className="px-3 pb-1 pt-3 font-ui text-[10px] font-bold uppercase tracking-[1.5px] text-ash-500">
          {label}
        </p>
        <ul className="flex flex-col gap-0.5">
          {rows.map((s) => renderRow(s))}
        </ul>
      </>
    );

  // ── Collapsed ChatGPT-style Rail ───────────────────────────────────────────
  if (!isOpen) {
    return (
      <>
        <aside
          className="fixed left-0 top-14 bottom-0 w-[68px] bg-ash-100 flex flex-col items-center py-3 px-2 z-50 border-r border-ash-200/70 transition-all duration-300 ease-in-out select-none"
        >
          {/* Middle Spacer - + button removed when sidebar is closed as requested */}
          <div className="flex-1" />

          {/* Bottom: User Profile Avatar */}
          <div className="mt-auto mb-3 relative" ref={profileMenuRef}>
            <button
              type="button"
              onClick={() => setProfileMenuOpen((v) => !v)}
              title={currentUser?.name || userEmail || 'Account Menu'}
              className={`relative flex items-center justify-center p-0.5 rounded-full transition-all duration-200 cursor-pointer ${
                profileMenuOpen
                  ? 'ring-2 ring-brand-500 ring-offset-2'
                  : 'hover:ring-2 hover:ring-brand-400/60 hover:ring-offset-1'
              }`}
              aria-label="Account Menu"
            >
              {renderAvatar('w-10 h-10 text-xs')}
              <span className="absolute bottom-0 right-0 h-3 w-3 rounded-full bg-emerald-500 ring-2 ring-white" />
            </button>

            {profileMenuOpen && (
              renderProfilePopup('left-[74px] bottom-0 w-72')
            )}
          </div>
        </aside>

        <DeactivateModal
          isOpen={deactivateModalOpen}
          onClose={() => setDeactivateModalOpen(false)}
          userEmail={userEmail}
        />
      </>
    );
  }

  // ── Expanded Full Sidebar ──────────────────────────────────────────────────
  return (
    <>
      <aside
        className="h-full w-72 fixed left-0 top-0 bg-ash-100 flex flex-col p-5 gap-y-4 z-50 border-r border-ash-200/70 transition-all duration-300 ease-in-out"
      >
        {/* Clicking anywhere else closes an open session menu. */}
        {menuFor && <div className="fixed inset-0 z-40" onClick={() => setMenuFor('')} />}

        <div className="flex items-center justify-between mb-2 px-1">
          <Link to="/" className="group flex items-center gap-2.5">
            <span
              aria-hidden="true"
              className="grad-brand flex h-8 w-8 items-center justify-center rounded-xl text-white shadow-glow transition-transform duration-300 group-hover:scale-105"
            >
              <span className="material-symbols-outlined text-[19px]">balance</span>
            </span>
            <span className="font-display text-[17px] font-bold tracking-[-0.02em] text-ash-900">
              Verdict<span className="grad-text">AI</span>
            </span>
          </Link>
          <button
            type="button"
            onClick={onToggleSidebar}
            title="Close sidebar"
            className="flex items-center justify-center h-8 w-8 rounded-lg text-ash-400 hover:text-ash-900 hover:bg-ash-200/60 transition-colors"
            aria-label="Close sidebar"
          >
            <span className="material-symbols-outlined text-[19px]">dock_to_left</span>
          </button>
        </div>

        <button
          onClick={onNewQuery}
          className="grad-btn flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 font-ui text-sm font-semibold text-white shadow-glow transition-all duration-300 hover:-translate-y-0.5 hover:shadow-glow-lg active:translate-y-0"
        >
          <span className="material-symbols-outlined">add</span>
          New Research Query
        </button>

        <div className="flex-1 min-h-0 overflow-y-auto overflow-x-visible -mx-2 px-2">
          {loading ? (
            <p className="px-3 pt-4 font-prose text-xs text-ash-500">Loading your research…</p>
          ) : sessions.length === 0 ? (
            <p className="px-3 pt-4 font-prose text-xs leading-relaxed text-ash-500">
              Your past research will appear here. Describe a case below to start.
            </p>
          ) : (
            <>
              {renderGroup('Pinned', pinned)}
              {renderGroup(pinned.length ? 'Recent' : 'Research history', rest)}
            </>
          )}
        </div>

        {/* User Profile Option at the Bottom of Sidebar */}
        <div className="mt-auto border-t border-ash-200/80 pt-3 relative" ref={profileMenuRef}>
          <button
            type="button"
            onClick={() => setProfileMenuOpen((v) => !v)}
            className={`flex w-full items-center gap-3 rounded-2xl p-2 text-left transition-all duration-200 cursor-pointer ${
              profileMenuOpen ? 'bg-white shadow-soft ring-1 ring-ash-200' : 'hover:bg-ash-200/60'
            }`}
            title="Account & Profile Menu"
          >
            <div className="relative shrink-0">
              {renderAvatar('w-9 h-9 text-xs')}
              <span className="absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full bg-emerald-500 ring-2 ring-white" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate font-ui text-[13px] font-semibold text-ash-900 leading-tight">
                {currentUser?.name || currentUser?.username || (userEmail ? userEmail.split('@')[0] : 'Legal Counsel')}
              </p>
              <p className="truncate font-ui text-[11px] text-ash-500 mt-0.5">
                {userEmail || currentUser?.email || 'Authenticated User'}
              </p>
            </div>
            <span className="material-symbols-outlined text-[19px] text-ash-400 shrink-0">
              {profileMenuOpen ? 'expand_less' : 'more_vert'}
            </span>
          </button>

          {profileMenuOpen && (
            renderProfilePopup('left-0 bottom-full mb-2 w-full')
          )}
        </div>
      </aside>

      <DeactivateModal
        isOpen={deactivateModalOpen}
        onClose={() => setDeactivateModalOpen(false)}
        userEmail={userEmail}
      />
    </>
  );
};

export default Sidebar;
