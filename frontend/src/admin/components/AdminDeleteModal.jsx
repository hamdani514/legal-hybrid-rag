import React from 'react';

const AdminDeleteModal = ({ isOpen, title, message, onConfirm, onCancel, confirmText = 'Delete' }) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-[100] animate-fade-in">
      <div className="bg-white rounded-2xl w-full max-w-md p-8 shadow-2xl relative border border-ash-100 flex flex-col gap-6">
        <div>
          <h3 className="font-display font-semibold text-xl text-[#111827]">{title || 'Confirm Deletion'}</h3>
          <p className="font-prose text-sm text-ash-500 mt-2">
            {message || 'Are you sure you want to delete this record? This action cannot be undone.'}
          </p>
        </div>

        <div className="flex justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={onCancel}
            className="px-5 py-2.5 rounded-lg border border-ash-200 text-ash-700 font-prose text-sm hover:bg-ash-50 transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="px-5 py-2.5 rounded-lg bg-[#DC2626] text-white font-prose text-sm font-semibold hover:bg-red-700 transition-colors"
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
};

export default AdminDeleteModal;
