import { useEffect, useRef, useState } from 'react';

// Users describe their case in 40-150 words (what happened, what each side
// claims, what the courts decided), so the box is a multi-line textarea that
// grows with the text. Enter adds a new line, as in any document; Ctrl+Enter
// (Cmd+Enter on macOS) sends.
const DEFAULT_PLACEHOLDER =
  "Describe your case: what happened, what each side claims, and what the courts decided so far. " +
  "Or ask a short legal question.";

const MAX_HEIGHT_PX = 260; // about ten lines, then the box scrolls

const ChatInput = ({ onSend, loading, placeholder = DEFAULT_PLACEHOLDER }) => {
  const [query, setQuery] = useState('');
  const textareaRef = useRef(null);

  // Auto-grow: reset to one row, then fit the content up to MAX_HEIGHT_PX.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT_PX)}px`;
    el.style.overflowY = el.scrollHeight > MAX_HEIGHT_PX ? 'auto' : 'hidden';
  }, [query]);

  const submit = () => {
    if (!query.trim() || loading) return;
    onSend(query.trim());
    setQuery('');
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    submit();
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      submit();
    }
    // Plain Enter falls through: the textarea inserts a newline.
  };

  const words = query.trim() ? query.trim().split(/\s+/).length : 0;

  return (
    <div className="fixed bottom-0 right-0 left-72 p-8 z-40 bg-gradient-to-t from-white via-white/95 to-transparent">
      <div className="max-w-4xl mx-auto relative">
        <form
          onSubmit={handleSubmit}
          className="glass-panel rounded-[28px] border border-ash-200 flex items-end gap-3 p-2 pr-3 focus-within:border-brand-300 focus-within:ring-4 focus-within:ring-brand-500/12 transition-all duration-250 shadow-card"
        >
          <textarea
            ref={textareaRef}
            rows={1}
            className="w-full resize-none bg-transparent border-none focus:ring-0 text-ash-900 placeholder:text-ash-400 font-prose py-4 pl-6 outline-none border-0 leading-relaxed"
            placeholder={placeholder}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
            aria-label="Describe your case or ask a legal question"
          />

          <button
            type="submit"
            disabled={loading || !query.trim()}
            title="Send (Ctrl+Enter)"
            className="grad-btn mb-1 flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full text-white shadow-glow transition-all duration-300 hover:scale-105 active:scale-95 disabled:cursor-not-allowed disabled:opacity-45 disabled:shadow-none"
          >
            {loading ? (
              <svg className="animate-spin h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
            ) : (
              <span className="material-symbols-outlined" style={{ fontVariationSettings: "'wght' 600" }}>
                arrow_upward
              </span>
            )}
          </button>
        </form>
        <p className="text-[10px] text-center text-ash-500 mt-3 uppercase tracking-wider">
          {words > 0 ? `${words} words · ` : ''}Enter for a new line · Ctrl+Enter to send · Verdict AI may provide general legal research; verify all findings with original statutes.
        </p>
      </div>
    </div>
  );
};

export default ChatInput;
