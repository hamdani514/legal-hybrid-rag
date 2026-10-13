import React, { useEffect, useState } from 'react';

/*
 * Pagination for the admin tables.
 *
 * At a few thousand judgments a button per page is unusable, so past
 * COMPACT_ABOVE pages the list collapses to: the first three, a window around
 * the page you are on, and the last three, with gaps shown as an ellipsis.
 * The page you are on is always in the list, however far from either end it
 * is, and a "Go to" box jumps straight to a page without clicking through.
 */

// Up to this many pages, every page is listed: collapsing would hide nothing.
const COMPACT_ABOVE = 7;
// The jump box only earns its space once there are more pages than this.
const JUMP_ABOVE = 5;
// Pages shown either side of the current one when the list is collapsed.
const WINDOW = 1;

/** Page buttons to render: {page} entries and {gap} separators, in order. */
export const pageItems = (currentPage, totalPages) => {
  if (totalPages <= COMPACT_ABOVE) {
    return Array.from({ length: totalPages }, (_, i) => ({ page: i + 1 }));
  }

  const wanted = new Set([1, 2, 3, totalPages - 2, totalPages - 1, totalPages]);
  for (let p = currentPage - WINDOW; p <= currentPage + WINDOW; p += 1) wanted.add(p);

  const pages = [...wanted].filter((p) => p >= 1 && p <= totalPages).sort((a, b) => a - b);

  const items = [];
  let previous = 0;
  pages.forEach((page) => {
    // An ellipsis hiding a single page costs the same width as the page
    // button, so show the page instead.
    if (previous && page - previous === 2) items.push({ page: previous + 1 });
    else if (previous && page - previous > 2) items.push({ gap: true, after: previous });
    items.push({ page });
    previous = page;
  });
  return items;
};

const AdminPagination = ({ currentPage, totalPages, onPageChange }) => {
  const [jumpValue, setJumpValue] = useState('');

  // Clear a half-typed page number when the page changes under us (a filter
  // was applied, a row was deleted, another button was clicked).
  useEffect(() => {
    setJumpValue('');
  }, [currentPage, totalPages]);

  if (totalPages <= 0) return null;

  const goTo = (page) => {
    const next = Math.min(Math.max(page, 1), totalPages);
    if (next !== currentPage) onPageChange(next);
  };

  const submitJump = (event) => {
    event.preventDefault();
    const page = parseInt(jumpValue, 10);
    if (Number.isFinite(page)) goTo(page);
    setJumpValue('');
  };

  const items = pageItems(currentPage, totalPages);
  const showJump = totalPages > JUMP_ABOVE;

  const arrow =
    'flex items-center gap-1 px-3 py-2 font-prose font-bold text-xs leading-4 text-[#6B7280] ' +
    'hover:text-[#111827] disabled:opacity-40 disabled:pointer-events-none transition-colors';

  return (
    <div
      className="px-6 sm:px-8 py-5 flex flex-wrap justify-between items-center gap-y-4 gap-x-3"
      style={{
        background: 'rgba(243, 244, 246, 0.2)',
        borderTop: '1px solid rgba(197, 198, 205, 0.1)',
      }}
    >
      <button
        type="button"
        disabled={currentPage <= 1}
        onClick={() => goTo(currentPage - 1)}
        className={arrow}
        aria-label="Previous page"
      >
        <span className="material-symbols-outlined" style={{ fontSize: '14px' }}>
          chevron_left
        </span>
        <span className="hidden sm:inline">Previous</span>
      </button>

      <div className="flex items-center gap-1.5 flex-wrap justify-center order-last w-full sm:order-none sm:w-auto">
        {items.map((item) =>
          item.gap ? (
            <span
              key={`gap-${item.after}`}
              aria-hidden="true"
              className="w-6 h-8 flex items-end justify-center font-prose text-xs text-ash-400 pb-1.5 select-none"
            >
              &hellip;
            </span>
          ) : (
            <button
              key={item.page}
              type="button"
              onClick={() => goTo(item.page)}
              aria-current={currentPage === item.page ? 'page' : undefined}
              aria-label={`Page ${item.page}`}
              className={`min-w-8 h-8 px-2 flex items-center justify-center font-prose font-bold text-xs rounded-[2px] transition-all ${
                currentPage === item.page
                  ? 'bg-[#111827] text-white'
                  : 'bg-transparent text-[#6B7280] hover:bg-ash-100 hover:text-[#111827]'
              }`}
            >
              {item.page}
            </button>
          )
        )}
      </div>

      <div className="flex items-center gap-3">
        {showJump && (
          <form onSubmit={submitJump} className="flex items-center gap-1.5">
            <label htmlFor="admin-page-jump" className="font-prose text-[11px] text-ash-500 whitespace-nowrap">
              Go to
            </label>
            <input
              id="admin-page-jump"
              type="number"
              inputMode="numeric"
              min={1}
              max={totalPages}
              value={jumpValue}
              onChange={(e) => setJumpValue(e.target.value)}
              placeholder={String(currentPage)}
              aria-label={`Go to page, 1 to ${totalPages}`}
              className="w-16 px-2 py-1.5 rounded-lg border border-ash-200 font-prose text-xs text-[#111827] text-center outline-none transition-all focus:border-[#0085FF] focus:ring-2 focus:ring-[#0085FF]/20 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
            />
            <span className="font-prose text-[11px] text-ash-400 whitespace-nowrap">of {totalPages}</span>
          </form>
        )}

        <button
          type="button"
          disabled={currentPage >= totalPages}
          onClick={() => goTo(currentPage + 1)}
          className={arrow}
          aria-label="Next page"
        >
          <span className="hidden sm:inline">Next</span>
          <span className="material-symbols-outlined" style={{ fontSize: '14px' }}>
            chevron_right
          </span>
        </button>
      </div>
    </div>
  );
};

export default AdminPagination;
