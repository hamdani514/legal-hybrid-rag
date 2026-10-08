import React, { useState } from 'react';

const UserFormModal = ({
  isOpen,
  onClose,
  isEditMode,
  errorMsg,
  successMsg,
  formData,
  setFormData,
  handleSubmit,
}) => {
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

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
            {isEditMode ? 'Edit User Details' : 'Add New User'}
          </h2>
          <p className="font-prose text-xs text-ash-500 mt-1">
            {isEditMode
              ? 'Modify details for the selected user profile.'
              : 'Create a new user profile with exact 5 registration fields.'}
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
          {/* First Name */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-bold text-ash-600 uppercase tracking-wider">First Name</label>
            <input
              type="text"
              required
              value={formData.firstName || ''}
              onChange={(e) => setFormData({ ...formData, firstName: e.target.value })}
              placeholder="e.g. Marcus"
              className="px-4 py-2.5 rounded-lg border border-ash-200 focus:border-[#0085FF] focus:ring-2 focus:ring-[#0085FF]/20 outline-none transition-all text-[#111827]"
            />
          </div>

          {/* Last Name */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-bold text-ash-600 uppercase tracking-wider">Last Name</label>
            <input
              type="text"
              required
              value={formData.lastName || ''}
              onChange={(e) => setFormData({ ...formData, lastName: e.target.value })}
              placeholder="e.g. Sterling"
              className="px-4 py-2.5 rounded-lg border border-ash-200 focus:border-[#0085FF] focus:ring-2 focus:ring-[#0085FF]/20 outline-none transition-all text-[#111827]"
            />
          </div>

          {/* Email Address */}
          <div className="flex flex-col gap-1.5 col-span-2">
            <label className="text-xs font-bold text-ash-600 uppercase tracking-wider">Email Address (Gmail Only)</label>
            <input
              type="email"
              required
              value={formData.email || ''}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              placeholder="e.g. user@gmail.com"
              className="px-4 py-2.5 rounded-lg border border-ash-200 focus:border-[#0085FF] focus:ring-2 focus:ring-[#0085FF]/20 outline-none transition-all text-[#111827]"
            />
          </div>

          {/* Password */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-bold text-ash-600 uppercase tracking-wider">Password</label>
            <div className="relative w-full">
              <input
                type={showPassword ? 'text' : 'password'}
                required={!isEditMode}
                value={formData.password || ''}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                placeholder={isEditMode ? 'Leave blank to keep current' : '••••••••'}
                className="w-full px-4 pr-10 py-2.5 rounded-lg border border-ash-200 focus:border-[#0085FF] focus:ring-2 focus:ring-[#0085FF]/20 outline-none transition-all text-[#111827]"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-ash-400 hover:text-ash-700 transition-colors flex items-center"
              >
                <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
                  {showPassword ? 'visibility_off' : 'visibility'}
                </span>
              </button>
            </div>
          </div>

          {/* Confirm Password */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-bold text-ash-600 uppercase tracking-wider">
              Confirm Password
            </label>
            <div className="relative w-full">
              <input
                type={showConfirmPassword ? 'text' : 'password'}
                required={!isEditMode}
                value={formData.confirmPassword || ''}
                onChange={(e) => setFormData({ ...formData, confirmPassword: e.target.value })}
                placeholder="••••••••"
                className="w-full px-4 pr-10 py-2.5 rounded-lg border border-ash-200 focus:border-[#0085FF] focus:ring-2 focus:ring-[#0085FF]/20 outline-none transition-all text-[#111827]"
              />
              <button
                type="button"
                onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-ash-400 hover:text-ash-700 transition-colors flex items-center"
              >
                <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
                  {showConfirmPassword ? 'visibility_off' : 'visibility'}
                </span>
              </button>
            </div>
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
              className="px-6 py-2.5 rounded-lg bg-[#111827] text-white font-bold hover:opacity-90 transition-opacity"
            >
              {isEditMode ? 'Save Changes' : 'Create User'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default UserFormModal;

