import React from 'react';

const SupportQueriesTable = ({
  loading,
  queries,
  sortedAndFilteredQueries,
  paginatedQueries,
  statusFilter,
  setStatusFilter,
  searchTerm,
  setSearchTerm,
  sortBy,
  setSortBy,
  setCurrentPage,
  handleStatusChange,
  setDeleteQueryId,
  getStatusStyle,
  formatDateTime,
  getInitials,
}) => {
  return (
    <div
      className="flex flex-col overflow-hidden rounded-3xl border border-ash-200 bg-white shadow-soft"
      style={{ boxShadow: '0px 0px 0px 1px rgba(197, 198, 205, 0.15)' }}
    >
      {/* Table Controls Header */}
      <div
        className="px-8 py-6 flex flex-col md:flex-row justify-between items-center gap-4"
        style={{ background: 'rgba(243, 244, 246, 0.5)' }}
      >
        <div className="flex flex-wrap gap-4 items-center w-full md:w-auto">
          {/* Status Filter Tabs */}
          <div className="flex items-center bg-[#E5E7EB] p-1 rounded-lg">
            {['All', 'Pending', 'Urgent', 'Solved'].map((st) => (
              <button
                key={st}
                onClick={() => {
                  setStatusFilter(st);
                  setCurrentPage(1);
                }}
                className={`px-4 py-1.5 font-prose text-xs font-bold rounded-md transition-all ${
                  statusFilter === st
                    ? 'bg-[#111827] text-white shadow-sm'
                    : 'text-[#6B7280] hover:text-[#111827]'
                }`}
              >
                {st}
              </button>
            ))}
          </div>

          {/* Search Input */}
          <div className="relative flex-1 md:flex-initial">
            <span
              className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[#6B7280]"
              style={{ fontSize: '14px' }}
            >
              search
            </span>
            <input
              type="text"
              placeholder="Search by name, email, query ID..."
              value={searchTerm}
              onChange={(e) => {
                setSearchTerm(e.target.value);
                setCurrentPage(1);
              }}
              className="pl-10 pr-4 py-2 bg-white text-sm leading-[17px] text-[#6B7280] font-prose rounded-lg w-full md:w-64 outline-none transition-all placeholder:text-[#6B7280]"
              style={{ boxShadow: '0px 0px 0px 1px rgba(197, 198, 205, 0.2)' }}
            />
          </div>

          {/* Sort Dropdown */}
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
              <option value="1_to_n">Order: Oldest to Newest</option>
              <option value="n_to_1">Order: Newest to Oldest</option>
            </select>
          </div>
        </div>

        <span className="font-prose font-medium text-xs text-[#4B5563]">
          Showing {sortedAndFilteredQueries.length} of {queries.length} inquiries
        </span>
      </div>

      {/* Queries Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-white" style={{ borderBottom: '1px solid rgba(197, 198, 205, 0.1)' }}>
              <th className="px-8 py-5 font-prose font-bold text-xs leading-4 tracking-[1.8px] uppercase text-[#6B7280]">
                Query ID
              </th>
              <th className="px-8 py-5 font-prose font-bold text-xs leading-4 tracking-[1.8px] uppercase text-[#6B7280]">
                Correspondent
              </th>
              <th className="px-8 py-5 font-prose font-bold text-xs leading-4 tracking-[1.8px] uppercase text-[#6B7280]">
                Subject & Message
              </th>
              <th className="px-8 py-5 font-prose font-bold text-xs leading-4 tracking-[1.8px] uppercase text-[#6B7280]">
                Timestamp
              </th>
              <th className="px-8 py-5 font-prose font-bold text-xs leading-4 tracking-[1.8px] uppercase text-[#6B7280]">
                Status
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
                  Loading support inquiries...
                </td>
              </tr>
            ) : sortedAndFilteredQueries.length === 0 ? (
              <tr>
                <td colSpan="6" className="px-8 py-10 text-center font-prose text-sm text-[#6B7280]">
                  No support inquiries match the criteria.
                </td>
              </tr>
            ) : (
              paginatedQueries.map((query, index) => {
                const { date, time } = formatDateTime(query.created_at);
                return (
                  <tr
                    key={query.query_id || index}
                    className="group hover:bg-[#F1F5F9] transition-colors"
                    style={{ borderTop: index > 0 ? '1px solid rgba(197, 198, 205, 0.05)' : 'none' }}
                  >
                    {/* Query ID */}
                    <td className="px-8 py-6 align-top">
                      <span className="font-mono text-sm font-semibold text-[#111827]">{query.query_id}</span>
                    </td>

                    {/* Correspondent */}
                    <td className="px-8 py-6 align-top">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-[#111827] text-white flex items-center justify-center font-bold text-xs flex-shrink-0">
                          {getInitials(query.full_name)}
                        </div>
                        <div className="flex flex-col">
                          <span className="font-display font-bold text-sm leading-5 text-[#111827]">
                            {query.full_name}
                          </span>
                          <span className="font-prose text-xs text-ash-500">{query.email}</span>
                        </div>
                      </div>
                    </td>

                    {/* Subject & Message */}
                    <td className="px-8 py-6 align-top max-w-md">
                      <div className="flex flex-col gap-1">
                        <span className="font-display font-semibold text-sm text-[#111827]">
                          {query.subject}
                        </span>
                        <p className="font-prose text-xs text-[#4B5563] leading-5 line-clamp-3">
                          {query.message}
                        </p>
                      </div>
                    </td>

                    {/* Timestamp */}
                    <td className="px-8 py-6 align-top">
                      <div className="flex flex-col">
                        <span className="font-prose text-xs text-[#111827] font-medium">{date}</span>
                        <span className="font-prose text-[10px] text-[#6B7280]">{time}</span>
                      </div>
                    </td>

                    {/* Status Dropdown */}
                    <td className="px-8 py-6 align-top">
                      <select
                        value={query.status || 'Pending'}
                        onChange={(e) => handleStatusChange(query.query_id, e.target.value)}
                        className={`px-3 py-1 font-prose font-bold text-[10px] leading-3 tracking-[1px] uppercase rounded-full outline-none border-0 transition-all cursor-pointer ${getStatusStyle(
                          query.status
                        )}`}
                      >
                        <option value="Pending">PENDING</option>
                        <option value="Urgent">URGENT</option>
                        <option value="Solved">SOLVED</option>
                      </select>
                    </td>

                    {/* Actions */}
                    <td className="px-8 py-6 align-top text-right">
                      <button
                        onClick={() => setDeleteQueryId(query.query_id)}
                        className="p-2 text-[#6B7280] hover:text-[#DC2626] transition-colors rounded-lg hover:bg-red-50"
                        title="Delete Inquiry"
                      >
                        <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
                          delete
                        </span>
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default SupportQueriesTable;
