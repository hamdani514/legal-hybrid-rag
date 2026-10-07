import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { relativeTime } from '../lib/chatHistory';

/*
 * The research sidebar: a new-query button and the user's saved conversations.
 *
 * A row shows its title and nothing else; the date is in the tooltip. On hover
 * (or while its menu is open) a three-dot button appears, holding the three
 * things you can do to a conversation: rename it, pin it to the top, delete it.
 * Renaming happens in place rather than in a dialog.
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
  setActiveTab,
}) => {
  const navigate = useNavigate();
  const [menuFor, setMenuFor] = useState('');
  const [renamingId, setRenamingId] = useState('');
  const [draft, setDraft] = useState('');
  const renameRef = useRef(null);

  useEffect(() => {
    if (renamingId && renameRef.current) {
      renameRef.current.focus();
      renameRef.current.select();
    }
  }, [renamingId]);

  // Escape closes whichever of the two is open.
  useEffect(() => {
    if (!menuFor && !renamingId) return undefined;
    const onKey = (e) => {
      if (e.key !== 'Escape') return;
      setMenuFor('');
      setRenamingId('');
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [menuFor, renamingId]);

  const startRename = (s) => {
    setMenuFor('');
    setDraft(s.title);
    setRenamingId(s.session_id);
  };

  const commitRename = async (s) => {
    const title = draft.trim();
    setRenamingId('');
    if (title && title !== s.title) await onRenameSession?.(s.session_id, title);
  };

  const pinned = sessions.filter((s) => s.pinned);
  const rest = sessions.filter((s) => !s.pinned);

  const Row = ({ s }) => {
    const isActive = s.session_id === activeSessionId && activeTab === 'case';
    const isMenuOpen = menuFor === s.session_id;

    if (renamingId === s.session_id) {
      return (
        <li>
          <input
            ref={renameRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => commitRename(s)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitRename(s);
              if (e.key === 'Escape') setRenamingId('');
            }}
            className="w-full rounded-lg border border-brand-500 bg-white px-3 py-2 font-prose text-[13px] text-ash-900 outline-none ring-2 ring-brand-100"
          />
        </li>
      );
    }

    return (
      <li className="group relative">
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

  const Group = ({ label, rows }) =>
    rows.length === 0 ? null : (
      <>
        <p className="px-3 pb-1 pt-3 font-ui text-[10px] font-bold uppercase tracking-[1.5px] text-ash-500">
          {label}
        </p>
        <ul className="flex flex-col gap-0.5">
          {rows.map((s) => (
            <Row key={s.session_id} s={s} />
          ))}
        </ul>
      </>
    );

  return (
    <aside className="h-full w-72 fixed left-0 top-0 bg-ash-100 flex flex-col p-6 gap-y-4 z-40 border-r border-ash-200/70">
      {/* Clicking anywhere else closes an open menu. */}
      {menuFor && <div className="fixed inset-0 z-40" onClick={() => setMenuFor('')} />}

      <div className="mb-6 px-2">
        <h1 className="font-display text-lg font-semibold text-ash-900">Verdict AI Research</h1>
        <p className="text-xs font-ui uppercase tracking-widest text-ash-600 mt-1">
          {userEmail ? userEmail.split('@')[0] : 'Senior Counsel'}
        </p>
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
            <Group label="Pinned" rows={pinned} />
            <Group label={pinned.length ? 'Recent' : 'Research history'} rows={rest} />
          </>
        )}
      </div>

      <div className="mt-auto border-t border-ash-200 pt-4 flex flex-col gap-y-1">
        {[
          { id: 'settings', label: 'Settings', icon: 'settings' },
          { id: 'support', label: 'Support', icon: 'help_outline' },
        ].map((item) => {
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => {
                if (item.id === 'settings') {
                  navigate('/settings');
                } else {
                  setActiveTab(isActive ? 'case' : item.id);
                }
              }}
              className={`flex w-full items-center gap-3 rounded-lg px-4 py-2 text-left transition-all duration-200 ${
                isActive ? 'bg-white font-medium text-ash-900 shadow-soft' : 'text-ash-600 hover:bg-ash-100'
              }`}
            >
              <span className="material-symbols-outlined">{item.icon}</span>
              <span className="font-ui text-sm tracking-wide">{item.label}</span>
            </button>
          );
        })}
      </div>
    </aside>
  );
};

export default Sidebar;
