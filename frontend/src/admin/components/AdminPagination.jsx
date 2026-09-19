import React from 'react';

const AdminPagination = ({ currentPage, totalPages, onPageChange }) => {
  if (totalPages <= 0) return null;

  return (
    <div
      className="px-8 py-6 flex justify-between items-center"
      style={{
        background: 'rgba(243, 244, 246, 0.2)',
        borderTop: '1px solid rgba(197, 198, 205, 0.1)',
      }}
    >
      <button
        disabled={currentPage === 1}
        onClick={() => onPageChange(Math.max(currentPage - 1, 1))}
        className="flex items-center gap-1 px-4 py-2 font-prose font-bold text-xs leading-4 text-[#6B7280] hover:text-[#111827] disabled:opacity-50 disabled:pointer-events-none transition-colors"
      >
        <span className="material-symbols-outlined" style={{ fontSize: '14px' }}>
          chevron_left
        </span>
        Previous
      </button>

      <div className="flex items-center gap-2">
        {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
          <button
            key={p}
            onClick={() => onPageChange(p)}
            className={`w-8 h-8 flex items-center justify-center font-prose font-bold text-xs rounded-[2px] transition-all ${
              currentPage === p
                ? 'bg-[#111827] text-white'
                : 'bg-transparent text-[#6B7280] hover:bg-ash-100 hover:text-[#111827]'
            }`}
          >
            {p}
          </button>
        ))}
      </div>

      <button
        disabled={currentPage === totalPages || totalPages === 0}
        onClick={() => onPageChange(Math.min(currentPage + 1, totalPages))}
        className="flex items-center gap-1 px-4 py-2 font-prose font-bold text-xs leading-4 text-[#6B7280] hover:text-[#111827] disabled:opacity-50 disabled:pointer-events-none transition-colors"
      >
        Next
        <span className="material-symbols-outlined" style={{ fontSize: '14px' }}>
          chevron_right
        </span>
      </button>
    </div>
  );
};

export default AdminPagination;
