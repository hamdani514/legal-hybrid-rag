import React from 'react';

const UserTable = ({
  loading,
  users,
  sortedAndFilteredUsers,
  paginatedUsers,
  filterQuery,
  setFilterQuery,
  sortBy,
  setSortBy,
  setCurrentPage,
  handlePlanChange,
  handleEditClick,
  handleDeleteClick,
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
              placeholder="Filter users..."
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
              <option value="name_asc">User: A to Z</option>
              <option value="name_desc">User: Z to A</option>
            </select>
          </div>
        </div>

        <span className="font-prose font-medium text-xs leading-4 text-[#4B5563]">
          Showing {sortedAndFilteredUsers.length} of {users.length} users
        </span>
      </div>

      {/* Data Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-white" style={{ borderBottom: '1px solid rgba(197, 198, 205, 0.1)' }}>
              <th className="px-8 py-5 font-prose font-bold text-xs leading-4 tracking-[1.8px] uppercase text-[#6B7280]">
                User ID
              </th>
              <th className="px-8 py-5 font-prose font-bold text-xs leading-4 tracking-[1.8px] uppercase text-[#6B7280]">
                Username
              </th>
              <th className="px-8 py-5 font-prose font-bold text-xs leading-4 tracking-[1.8px] uppercase text-[#6B7280]">
                Email
              </th>
              <th className="px-8 py-5 font-prose font-bold text-xs leading-4 tracking-[1.8px] uppercase text-[#6B7280]">
                Organization
              </th>
              <th className="px-8 py-5 font-prose font-bold text-xs leading-4 tracking-[1.8px] uppercase text-[#6B7280]">
                Plan
              </th>
              <th className="px-8 py-5 font-prose font-bold text-xs leading-4 tracking-[1.8px] uppercase text-[#6B7280]">
                Phone No
              </th>
              <th className="px-8 py-5 font-prose font-bold text-xs leading-4 tracking-[1.8px] uppercase text-[#6B7280] text-right">
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan="7" className="px-8 py-10 text-center font-prose text-sm text-[#6B7280]">
                  Loading registered users...
                </td>
              </tr>
            ) : sortedAndFilteredUsers.length === 0 ? (
              <tr>
                <td colSpan="7" className="px-8 py-10 text-center font-prose text-sm text-[#6B7280]">
                  No users found.
                </td>
              </tr>
            ) : (
              paginatedUsers.map((user, index) => (
                <tr
                  key={user.id || index}
                  className="group hover:bg-[#F1F5F9] transition-colors"
                  style={{ borderTop: index > 0 ? '1px solid rgba(197, 198, 205, 0.05)' : 'none' }}
                >
                  <td className="px-8 py-6">
                    <span className="font-mono text-sm font-semibold text-[#111827]">{user.id}</span>
                  </td>

                  <td className="px-8 py-6">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg bg-[#111827] text-white flex items-center justify-center font-bold text-xs ring-1 ring-transparent group-hover:ring-[#0085FF] transition-all flex-shrink-0">
                        {getInitials(user.name)}
                      </div>
                      <div className="flex flex-col">
                        <span className="font-display font-bold text-sm leading-5 text-[#111827]">{user.name}</span>
                        <span className="font-prose text-xs text-ash-500">@{user.username}</span>
                      </div>
                    </div>
                  </td>

                  <td className="px-8 py-6">
                    <span className="font-prose text-sm text-[#4B5563]">{user.email}</span>
                  </td>

                  <td className="px-8 py-6">
                    <span className="font-prose font-medium text-sm leading-5 text-[#111827]">{user.org}</span>
                  </td>

                  <td className="px-8 py-6">
                    <select
                      value={user.plan}
                      onChange={(e) => handlePlanChange(user.id, e.target.value)}
                      className={`appearance-none cursor-pointer px-3 py-1 font-prose font-bold text-[10px] leading-3 tracking-[1px] uppercase rounded-full outline-none border-0 transition-all ${
                        user.plan === 'Pro' ? 'bg-brand-100 text-brand-800' : 'bg-[#E5E7EB] text-[#4B5563]'
                      }`}
                      style={{ backgroundImage: 'none' }}
                    >
                      <option value="Standard">STANDARD</option>
                      <option value="Pro">PRO</option>
                    </select>
                  </td>

                  <td className="px-8 py-6">
                    <span className="font-prose text-sm text-[#4B5563]">{user.phone_no || 'N/A'}</span>
                  </td>

                  <td className="px-8 py-6 text-right">
                    <div className="flex justify-end gap-3">
                      <button
                        onClick={() => handleEditClick(user)}
                        className="p-2 text-[#6B7280] hover:text-[#111827] transition-colors"
                        title="Edit User"
                      >
                        <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
                          edit_note
                        </span>
                      </button>
                      <button
                        onClick={() => handleDeleteClick(user)}
                        className="p-2 text-[#6B7280] hover:text-[#DC2626] transition-colors"
                        title="Delete User"
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

export default UserTable;
