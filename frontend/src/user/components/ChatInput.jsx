import { useState } from 'react';

const ChatInput = ({ onSend, loading, placeholder = "Ask your legal query..." }) => {
  const [query, setQuery] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!query.trim() || loading) return;
    onSend(query.trim());
    setQuery('');
  };

  return (
    <div className="fixed bottom-0 right-0 left-72 p-8 z-40 bg-gradient-to-t from-white via-white/95 to-transparent">
      <div className="max-w-4xl mx-auto relative">
        <form
          onSubmit={handleSubmit}
          className="glass-panel rounded-full border border-ash-200 flex items-center gap-3 p-2 pr-3 focus-within:border-brand-300 focus-within:ring-4 focus-within:ring-brand-500/12 transition-all duration-250 shadow-card"
        >
          <input
            type="text"
            className="w-full bg-transparent border-none focus:ring-0 text-ash-900 placeholder:text-ash-400 font-prose py-4 pl-6 outline-none border-0"
            placeholder={placeholder}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={loading}
          />
          
          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="grad-btn flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full text-white shadow-glow transition-all duration-300 hover:scale-105 active:scale-95 disabled:cursor-not-allowed disabled:opacity-45 disabled:shadow-none"
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
          The Digital Atelier AI may provide general legal research; verify all findings with original statutes.
        </p>
      </div>
    </div>
  );
};

export default ChatInput;
