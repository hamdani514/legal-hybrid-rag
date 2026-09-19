import React from 'react';

const AdminTable = ({
  loading,
  admins,
  sortedAndFilteredAdmins,
  paginatedAdmins,
  filterQuery,
  setFilterQuery,
  sortBy,
  setSortBy,
  setCurrentPage,
  visiblePasswords,
  togglePasswordVisibility,
  handleEditClick,
  handleDeleteClick,
  currentAdmin,
  getInitials,
}) => {
  return (
    <div
      className="flex flex-col overflow-hidden rounded-3xl border border-ash-200 bg-white shadow-soft"
      style={{ boxShadow: '0px 0px 0px 1px rgba(197, 198, 205, 0.15)' }}
    >
      {/* Table Header Controls */}
      <div
        className="px-8 py-6 flex justify-between items-center"
        style={{ background: 'rgba(243, 244, 246, 0.5)' }}
      >
        <div className="flex gap-4 items-center">
          {/* Search Input */}
          <div className="relative">
            <span
              className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[#6B7280]"
              style={{ fontSize: '14px' }}
            >
              search
            </span>
            <input
              type="text"
              placeholder="Filter administrators..."
              value={filterQuery}
              onChange={(e) => {
                setFilterQuery(e.target.value);
                setCurrentPage(1);
              }}
              className="w-64 rounded-xl border border-ash-200 bg-white py-2.5 pl-10 pr-4 font-prose text-sm text-ash-900 placeholder:text-ash-400 outline-none transition-all duration-250 focus:border-brand-400 focus:ring-4 focus:ring-brand-500/12"
              style={{ boxShadow: '0px 0px 0px 1px rgba(197, 198, 205, 0.2)' }}
            />
          </div>

          {/* Sort Splitter Dropdown */}
          <div
            className="relative flex items-center gap-2 bg-white px-3 py-2 rounded-lg"
            style={{ boxShadow: '0px 0px 0px 1px rgba(197, 198, 205, 0.2)' }}
          >
            <span className="material-symbols-outlined text-[#6B7280]" style={{ fontSize: '16px' }}>
              sort
            </span>
            <select
              value={sortBy}
              onChange={(e) => {
                setSortBy(e.target.value);
                setCurrentPage(1);
              }}
              className="bg-transparent text-sm text-[#6B7280] font-prose outline-none cursor-pointer pr-4"
            >
              <option value="id_asc">ID: 1 to n</option>
              <option value="id_desc">ID: n to 1</option>
              <option value="name_asc">Name: A to Z</option>
              <option value="name_desc">Name: Z to A</option>
            </select>
          </div>
        </div>

        <span className="font-prose font-medium text-xs leading-4 text-[#4B5563]">
          Showing {sortedAndFilteredAdmins.length} of {admins.length} administrators
        </span>
      </div>

      {/* Data Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-white" style={{ borderBottom: '1px solid rgba(197, 198, 205, 0.1)' }}>
              <th className="px-8 py-5 font-prose font-bold text-xs leading-4 tracking-[1.8px] uppercase text-[#6B7280]">
                Admin Identity
              </th>
              <th className="px-8 py-5 font-prose font-bold text-xs leading-4 tracking-[1.8px] uppercase text-[#6B7280]">
                Admin ID / Email
              </th>
              <th className="px-8 py-5 font-prose font-bold text-xs leading-4 tracking-[1.8px] uppercase text-[#6B7280]">
                Role
              </th>
              <th className="px-8 py-5 font-prose font-bold text-xs leading-4 tracking-[1.8px] uppercase text-[#6B7280]">
                Date of Birth
              </th>
              <th className="px-8 py-5 font-prose font-bold text-xs leading-4 tracking-[1.8px] uppercase text-[#6B7280]">
                Encrypted Password
              </th>
              <th className="px-8 py-5 font-prose font-bold text-xs leading-4 tracking-[1.8px] uppercase text-[#6B7280] text-right">
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan="6" className="px-8 py-10 text-center font-prose text-sm text-[#6B7280]">
                  Loading system administrators...
                </td>
              </tr>
            ) : sortedAndFilteredAdmins.length === 0 ? (
              <tr>
                <td colSpan="6" className="px-8 py-10 text-center font-prose text-sm text-[#6B7280]">
                  No system administrators found.
                </td>
              </tr>
            ) : (
              paginatedAdmins.map((admin, index) => (
                <tr
                  key={admin.adminid || index}
                  className="group hover:bg-[#F1F5F9] transition-colors"
                  style={{ borderTop: index > 0 ? '1px solid rgba(197, 198, 205, 0.05)' : 'none' }}
                >
                  {/* Identity */}
                  <td className="px-8 py-6">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg bg-[#111827] text-[#0085FF] flex items-center justify-center font-bold text-xs ring-1 ring-transparent group-hover:ring-[#0085FF] transition-all flex-shrink-0">
                        {getInitials(admin.name)}
                      </div>
                      <div className="flex flex-col">
                        <span className="font-display font-bold text-sm leading-5 text-[#111827]">
                          {admin.name}
                        </span>
                        {admin.adminid === currentAdmin?.adminid && (
                          <span className="text-[10px] text-mint-600 font-bold uppercase tracking-wider">
                            (Current User)
                          </span>
                        )}
                      </div>
                    </div>
                  </td>

                  {/* Admin ID / Email */}
                  <td className="px-8 py-6">
                    <span className="font-prose text-sm text-[#4B5563] font-mono">{admin.adminid}</span>
                  </td>

                  {/* Role */}
                  <td className="px-8 py-6">
                    <span
                      className={`inline-block px-3 py-1 font-prose font-bold text-[10px] leading-3 tracking-[1px] uppercase rounded-full ${
                        admin.role === 'super_admin'
                          ? 'bg-brand-100 text-brand-800'
                          : 'bg-[#E5E7EB] text-[#4B5563]'
                      }`}
                    >
                      {admin.role === 'super_admin' ? 'SUPER ADMIN' : 'ADMIN'}
                    </span>
                  </td>

                  {/* DOB */}
                  <td className="px-8 py-6">
                    <span className="font-prose text-sm text-[#4B5563]">{admin.dob || 'N/A'}</span>
                  </td>

                  {/* Password Eye Toggle */}
                  <td className="px-8 py-6">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm text-[#4B5563]">
                        {visiblePasswords[admin.adminid] ? admin.password : '••••••••••••'}
                      </span>
                      <button
                        onClick={() => togglePasswordVisibility(admin.adminid)}
                        className="text-ash-400 hover:text-ash-600 transition-colors p-1"
                        title={visiblePasswords[admin.adminid] ? 'Hide Password' : 'Show Password'}
                      >
                        <span className="material-symbols-outlined text-base">
                          {visiblePasswords[admin.adminid] ? 'visibility_off' : 'visibility'}
                        </span>
                      </button>
                    </div>
                  </td>

                  {/* Actions */}
                  <td className="px-8 py-6 text-right">
                    <div className="flex justify-end gap-3">
                      <button
                        onClick={() => handleEditClick(admin)}
                        className="p-2 text-[#6B7280] hover:text-[#111827] transition-colors"
                        title="Edit Admin"
                      >
                        <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
                          edit_note
                        </span>
                      </button>
                      <button
                        onClick={() => handleDeleteClick(admin)}
                        disabled={admin.adminid === currentAdmin?.adminid}
                        className={`p-2 transition-colors ${
                          admin.adminid === currentAdmin?.adminid
                            ? 'text-ash-300 cursor-not-allowed'
                            : 'text-[#6B7280] hover:text-[#DC2626]'
                        }`}
                        title={
                          admin.adminid === currentAdmin?.adminid
                            ? 'Cannot delete yourself'
                            : 'Delete Admin'
                        }
                      >
                        <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
                          delete
                        </span>
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default AdminTable;
