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
  const [showPassword, setShowPassword] = React.useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = React.useState(false);

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

          {/* Assigned System Permissions */}
          <div className="flex flex-col gap-2 col-span-2 bg-ash-50 p-4 rounded-xl border border-ash-200">
            <label className="text-xs font-bold text-ash-700 uppercase tracking-wider flex items-center gap-1.5">
              <span className="material-symbols-outlined text-[16px] text-[#0085FF]">shield</span>
              Assigned Permissions & Capabilities
            </label>
            <p className="text-[11px] text-ash-500 font-prose mb-1">
              Select which areas this administrator is authorized to access and manage:
            </p>
            
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <label className="flex items-center gap-2 p-2.5 rounded-lg border border-ash-200 bg-white cursor-pointer hover:border-[#0085FF] transition-all">
                <input
                  type="checkbox"
                  checked={(formData.permissions || []).includes('cases')}
                  onChange={(e) => {
                    const current = formData.permissions || [];
                    const next = e.target.checked
                      ? [...current, 'cases']
                      : current.filter((p) => p !== 'cases');
                    setFormData({ ...formData, permissions: next });
                  }}
                  className="rounded text-[#0085FF] focus:ring-[#0085FF]"
                />
                <div className="flex flex-col">
                  <span className="text-xs font-bold text-ash-900">Case Upload</span>
                  <span className="text-[10px] text-ash-500">Ingestion pipeline</span>
                </div>
              </label>

              <label className="flex items-center gap-2 p-2.5 rounded-lg border border-ash-200 bg-white cursor-pointer hover:border-[#0085FF] transition-all">
                <input
                  type="checkbox"
                  checked={(formData.permissions || []).includes('users')}
                  onChange={(e) => {
                    const current = formData.permissions || [];
                    const next = e.target.checked
                      ? [...current, 'users']
                      : current.filter((p) => p !== 'users');
                    setFormData({ ...formData, permissions: next });
                  }}
                  className="rounded text-[#0085FF] focus:ring-[#0085FF]"
                />
                <div className="flex flex-col">
                  <span className="text-xs font-bold text-ash-900">User Management</span>
                  <span className="text-[10px] text-ash-500">View & manage users</span>
                </div>
              </label>

              <label className="flex items-center gap-2 p-2.5 rounded-lg border border-ash-200 bg-white cursor-pointer hover:border-[#0085FF] transition-all">
                <input
                  type="checkbox"
                  checked={(formData.permissions || []).includes('support')}
                  onChange={(e) => {
                    const current = formData.permissions || [];
                    const next = e.target.checked
                      ? [...current, 'support']
                      : current.filter((p) => p !== 'support');
                    setFormData({ ...formData, permissions: next });
                  }}
                  className="rounded text-[#0085FF] focus:ring-[#0085FF]"
                />
                <div className="flex flex-col">
                  <span className="text-xs font-bold text-ash-900">Support Queries</span>
                  <span className="text-[10px] text-ash-500">Manage help tickets</span>
                </div>
              </label>
            </div>
          </div>

          {/* Password */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-bold text-ash-600 uppercase tracking-wider">Password</label>
            <div className="relative w-full">
              <input
                type={showPassword ? 'text' : 'password'}
                required={!isEditMode}
                value={formData.password}
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
                value={formData.confirmPassword}
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
