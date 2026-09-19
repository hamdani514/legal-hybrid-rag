import React from 'react';

const AdminFormModal = ({
  isOpen,
  onClose,
  isEditMode,
  errorMsg,
  successMsg,
  formData,
  setFormData,
  handleSubmit,
  saving,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-[100] animate-fade-in">
      <div className="bg-white rounded-2xl w-full max-w-xl max-h-[90vh] overflow-y-auto p-8 shadow-2xl relative border border-ash-100 flex flex-col gap-6">
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-ash-400 hover:text-ash-600 transition-colors"
        >
          <span className="material-symbols-outlined" style={{ fontSize: '24px' }}>
            close
          </span>
        </button>

        <div>
          <h2 className="font-display font-semibold text-2xl text-[#111827]">
            {isEditMode ? 'Edit Administrator' : 'Add New Administrator'}
          </h2>
          <p className="font-prose text-xs text-ash-500 mt-1">
            {isEditMode
              ? 'Modify details and permissions for this administrator account.'
              : 'Create a new administrative account with specific system role permissions.'}
          </p>
        </div>

        {errorMsg && (
          <div role="alert" className="flex items-start gap-2.5 bg-red-50 text-red-700 p-4 rounded-xl text-xs font-prose border border-red-100">
            <span className="material-symbols-outlined shrink-0 text-base leading-5" aria-hidden="true">
              error
            </span>
            <span>{errorMsg}</span>
          </div>
        )}

        {successMsg && (
          <div role="status" className="flex items-start gap-2.5 bg-mint-400/10 text-mint-700 p-4 rounded-xl text-xs font-prose border border-mint-400/30">
            <span className="material-symbols-outlined shrink-0 text-base leading-5" aria-hidden="true">
              check_circle
            </span>
            <span>{successMsg}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-6 font-prose text-sm">
          {/* Full Name */}
          <div className="flex flex-col gap-1.5 col-span-2">
            <label className="text-xs font-bold text-ash-600 uppercase tracking-wider">Full Name</label>
            <input
              type="text"
              required
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder="e.g. Eleanor Vance"
              className="px-4 py-2.5 rounded-lg border border-ash-200 focus:border-[#0085FF] focus:ring-2 focus:ring-[#0085FF]/20 outline-none transition-all text-[#111827]"
            />
          </div>

          {/* Admin ID / Email */}
          <div className="flex flex-col gap-1.5 col-span-2">
            <label className="text-xs font-bold text-ash-600 uppercase tracking-wider">
              Admin ID (Email Address)
            </label>
            <input
              type="text"
              required
              disabled={isEditMode}
              value={formData.adminid}
              onChange={(e) => setFormData({ ...formData, adminid: e.target.value, email: e.target.value })}
              placeholder="e.g. AdminEleanor@cust.com"
              className={`px-4 py-2.5 rounded-lg border border-ash-200 focus:border-[#0085FF] focus:ring-2 focus:ring-[#0085FF]/20 outline-none transition-all text-[#111827] ${
                isEditMode ? 'bg-ash-100 cursor-not-allowed' : ''
              }`}
            />
          </div>

          {/* System Role */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-bold text-ash-600 uppercase tracking-wider">Role</label>
            <select
              value={formData.role}
              onChange={(e) => setFormData({ ...formData, role: e.target.value })}
              className="px-4 py-2.5 rounded-lg border border-ash-200 focus:border-[#0085FF] focus:ring-2 focus:ring-[#0085FF]/20 outline-none transition-all text-[#111827] bg-white cursor-pointer"
            >
              <option value="admin">Administrator</option>
              <option value="super_admin">Super Administrator</option>
            </select>
          </div>

          {/* DOB */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-bold text-ash-600 uppercase tracking-wider">Date of Birth</label>
            <input
              type="date"
              required
              value={formData.dob}
              onChange={(e) => setFormData({ ...formData, dob: e.target.value })}
              className="px-4 py-2.5 rounded-lg border border-ash-200 focus:border-[#0085FF] focus:ring-2 focus:ring-[#0085FF]/20 outline-none transition-all text-[#111827]"
            />
          </div>

          {/* Password */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-bold text-ash-600 uppercase tracking-wider">Password</label>
            <input
              type="password"
              required
              value={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              placeholder="••••••••"
              className="px-4 py-2.5 rounded-lg border border-ash-200 focus:border-[#0085FF] focus:ring-2 focus:ring-[#0085FF]/20 outline-none transition-all text-[#111827]"
            />
          </div>

          {/* Confirm Password */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-bold text-ash-600 uppercase tracking-wider">
              Confirm Password
            </label>
            <input
              type="password"
              required
              value={formData.confirmPassword}
              onChange={(e) => setFormData({ ...formData, confirmPassword: e.target.value })}
              placeholder="••••••••"
              className="px-4 py-2.5 rounded-lg border border-ash-200 focus:border-[#0085FF] focus:ring-2 focus:ring-[#0085FF]/20 outline-none transition-all text-[#111827]"
            />
          </div>

          {/* Modal Actions */}
          <div className="col-span-2 flex justify-end gap-3 pt-4 border-t border-ash-100">
            <button
              type="button"
              onClick={onClose}
              className="px-5 py-2.5 rounded-lg border border-ash-200 text-ash-700 hover:bg-ash-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-6 py-2.5 rounded-lg bg-[#111827] text-white font-bold hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {saving ? 'Saving...' : isEditMode ? 'Save Changes' : 'Create Admin'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default AdminFormModal;
