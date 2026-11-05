import { useCallback, useEffect, useRef, useState } from 'react';
import FilterDialog, { EMPTY_FILTERS, activeFilterCount } from './ResultsFilter';
import { LockedButton, UpgradeDialog } from './LockedFeature';
import Modal from './Modal';
import FilterIcon from './FilterIcon';
import { usePlan } from '../lib/plan';
import { filterChips } from '../lib/filterSummary';

// Users describe their case in 40-150 words (what happened, what each side
// claims, what the courts decided), so the box is a multi-line textarea that
// grows with the text. Enter sends; Shift+Enter adds a new line.
const DEFAULT_PLACEHOLDER = 'Describe your case or ask a legal question';

const MAX_HEIGHT_PX = 260; // about ten lines, then the box scrolls

const ChatInput = ({
  onSend,
  loading,
  placeholder = DEFAULT_PLACEHOLDER,
  sidebarOpen = true,
  mobile = false,
  filters = EMPTY_FILTERS,
  onFiltersChange,
}) => {
  const [query, setQuery] = useState('');
  const [showFilter, setShowFilter] = useState(false);
  const [showUpgrade, setShowUpgrade] = useState(false);
  const closeFilter = useCallback(() => setShowFilter(false), []);
  const closeUpgrade = useCallback(() => setShowUpgrade(false), []);
  const plan = usePlan();
  const canFilter = Boolean(plan.features.filter);
  const chips = filterChips(filters);
  const textareaRef = useRef(null);

  // Auto-grow: reset to one row, then fit the content up to MAX_HEIGHT_PX.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    // One row, set in pixels rather than left to `height: auto`: the box must
    // not open up for a wrapping placeholder or for styles added to the page
    // from outside (browser extensions inject their own into text boxes).
    const box = getComputedStyle(el);
    const oneRow =
      parseFloat(box.lineHeight) + parseFloat(box.paddingTop) + parseFloat(box.paddingBottom);
    el.style.height = Number.isFinite(oneRow) ? `${oneRow}px` : 'auto';
    if (!query) {
      el.style.overflowY = 'hidden';
      return;
    }
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
    // isComposing: Enter is confirming a word in an input method (Urdu, for
    // one), not sending.
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
    // Shift+Enter falls through: the textarea inserts a newline.
  };

  const words = query.trim() ? query.trim().split(/\s+/).length : 0;

  return (
    <>
    <div className={`fixed bottom-0 right-0 ${mobile ? 'left-0 p-3' : `${sidebarOpen ? 'left-72' : 'left-[68px]'} p-8`} z-40 bg-gradient-to-t from-white via-white/95 to-transparent pointer-events-none transition-[left] duration-300 ease-in-out`}>
      <div className="max-w-4xl mx-auto relative pointer-events-auto">
        {/* Filters chosen for the next search: visible before sending, and
            removable without opening the dialog. */}
        {chips.length > 0 && (
          <div className="mb-2 flex flex-wrap items-center gap-1.5 rounded-2xl border border-brand-100 bg-brand-50/95 px-3 py-2 backdrop-blur-sm">
            <span className="flex items-center gap-1 font-ui text-[11px] font-bold text-brand-700">
              <FilterIcon size={14} />
              Filters for this search:
            </span>
            {chips.map((chip) => (
              <span
                key={chip}
                className="rounded-full bg-white px-2.5 py-0.5 font-ui text-[11px] font-semibold text-brand-700 ring-1 ring-brand-100"
              >
                {chip}
              </span>
            ))}
            <button
              type="button"
              onClick={() => onFiltersChange?.(EMPTY_FILTERS)}
              className="ml-auto rounded-full border border-ash-300 bg-white px-3 py-1 font-ui text-[11px] font-bold text-ash-600 transition-colors hover:border-brand-300 hover:text-brand-700"
            >
              Reset
            </button>
          </div>
        )}
        <form
          onSubmit={handleSubmit}
          className="chat-input-form glass-panel rounded-[28px] border border-ash-200 flex items-end gap-3 p-2 pr-3 focus-within:border-brand-400 focus-within:shadow-[0_4px_20px_rgba(0,133,255,0.08)] transition-all duration-200 shadow-card outline-none"
        >
          <textarea
            ref={textareaRef}
            rows={1}
            className="w-full resize-none bg-transparent border-none focus:ring-0 text-ash-900 placeholder:truncate placeholder:text-ash-400 font-prose py-4 pl-4 sm:pl-6 outline-none border-0 leading-relaxed shadow-none focus:outline-none"
            placeholder={placeholder}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
            aria-label="Describe your case or ask a legal question"
          />

          {canFilter ? (
            <button
              type="button"
              onClick={() => setShowFilter(true)}
              disabled={loading}
              aria-haspopup="dialog"
              aria-label={
                chips.length
                  ? `Filters for this search: ${activeFilterCount(filters)} set. Change them.`
                  : 'Add filters to this search'
              }
              title="Filter the results of this search"
              className={`mb-2 inline-flex h-10 flex-shrink-0 items-center gap-1.5 rounded-full border px-3.5 font-ui text-[13px] font-semibold transition-all disabled:cursor-not-allowed disabled:opacity-50 ${
                chips.length
                  ? 'border-brand-300 bg-brand-50 text-brand-700'
                  : 'border-ash-300 bg-white text-ash-700 hover:border-brand-300 hover:text-brand-700'
              }`}
            >
              <FilterIcon size={15} />
              <span className="hidden sm:inline">Filter</span>
              {chips.length > 0 && (
                <span className="inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-brand-600 px-1 font-ui text-[10px] font-bold text-white">
                  {activeFilterCount(filters)}
                </span>
              )}
            </button>
          ) : (
            <span className="mb-2.5 flex-shrink-0">
              <LockedButton
                feature="filter"
                icon={<FilterIcon size={14} />}
                label="Filter"
                size="sm"
                compact={mobile}
                onLocked={() => setShowUpgrade(true)}
              />
            </span>
          )}

          <button
            type="submit"
            disabled={loading || !query.trim()}
            title="Send (Enter)"
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
          {words > 0 ? `${words} words · ` : ''}Enter to send · Shift+Enter for a new line<span className="hidden sm:inline"> · Verdict AI may provide general legal research; verify all findings with original statutes.</span>
        </p>
      </div>
    </div>

    {/* Outside the fixed bar, whose z-index would otherwise cap the dialogs
        below the sidebar. */}
    {showFilter && (
      <FilterDialog
        filters={filters}
        onApply={(next) => onFiltersChange?.(next)}
        onClose={closeFilter}
        Modal={Modal}
        beforeSearch
      />
    )}
    {showUpgrade && <UpgradeDialog feature="filter" onClose={closeUpgrade} />}
    </>
  );
};

export default ChatInput;
