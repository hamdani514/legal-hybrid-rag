import React from 'react';
import AdminPagination from './AdminPagination';

const RecentJobsTable = ({
  recentLoading,
  recentError,
  allJobs = [],
  filteredJobs = [],
  paginatedJobs = [],
  searchTerm,
  setSearchTerm,
  currentPage,
  setCurrentPage,
  totalPages,
  formatRelativeTime,
  setShowAllModal,
  setDeleteTarget,
}) => {
  return (
    <div className="flex flex-col overflow-hidden rounded-3xl border border-ash-200 bg-white shadow-soft">
      {/* Header with Search & View All History Modal Trigger */}
      <div className="p-8 pb-6 border-b border-ash-100 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h3 className="font-display font-bold text-xl text-[#111827]">Case Ingestion History</h3>
          <p className="font-prose text-xs text-ash-500 mt-1">Manage, search, and navigate through uploaded judgment PDF files.</p>
        </div>

        <div className="flex items-center gap-4 w-full md:w-auto">
          {/* Search Input Box */}
          <div className="relative flex-1 md:w-64">
            <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[#6B7280]" style={{ fontSize: '16px' }}>
              search
            </span>
            <input
              type="text"
              placeholder="Search case by title or ID..."
              value={searchTerm}
              onChange={(e) => {
                setSearchTerm(e.target.value);
                setCurrentPage(1);
              }}
              className="w-full pl-9 pr-4 py-2 bg-[#F1F5F9] text-xs font-prose text-[#111827] rounded-lg outline-none focus:ring-1 focus:ring-[#0085FF]"
            />
          </div>
        </div>
      </div>

      {recentError && (
        <div role="alert" className="flex items-start gap-2.5 mx-8 mt-4 bg-red-50 text-red-700 p-4 rounded-xl text-xs font-prose">
          <span className="material-symbols-outlined shrink-0 text-base leading-5" aria-hidden="true">
            error
          </span>
          <span>{recentError}</span>
        </div>
      )}

      {/* Counter Banner */}
      <div className="px-8 py-3 bg-[#F8FAFC] border-b border-ash-100 flex justify-between items-center text-xs font-prose text-[#6B7280]">
        <span>
          Showing {paginatedJobs.length} of {filteredJobs.length} judgment cases
        </span>
        {searchTerm && (
          <span className="text-[#111827] font-semibold">
            Filtered from {allJobs.length} total uploads
          </span>
        )}
      </div>

      {/* Data Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-ash-100 font-prose text-xs font-bold text-ash-400 uppercase tracking-wider bg-ash-50/50">
              <th className="py-4 px-8">Filename / Judgment Title</th>
              <th className="py-4 px-6">Job ID</th>
              <th className="py-4 px-6">Status</th>
              <th className="py-4 px-6">Uploaded</th>
              <th className="py-4 px-8 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="font-prose text-sm divide-y divide-ash-50">
            {recentLoading ? (
              <tr>
                <td colSpan="5" className="py-10 text-center text-ash-400">
                  Loading ingestion activity...
                </td>
              </tr>
            ) : filteredJobs.length === 0 ? (
              <tr>
                <td colSpan="5" className="py-10 text-center text-ash-400">
                  {searchTerm ? 'No cases match your search query.' : 'No ingestion jobs recorded.'}
                </td>
              </tr>
            ) : (
              paginatedJobs.map((job) => (
                <tr key={job.job_id} className="hover:bg-ash-50/80 transition-colors">
                  <td className="py-4 px-8 font-medium text-[#111827]">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg bg-[#111827]/5 text-[#111827] flex items-center justify-center flex-shrink-0">
                        <span className="material-symbols-outlined text-base">description</span>
                      </div>
                      <span className="truncate max-w-sm font-semibold">{job.filename || 'Unnamed document'}</span>
                    </div>
                  </td>
                  <td className="py-4 px-6 font-mono text-xs text-ash-500">{job.job_id}</td>
                  <td className="py-4 px-6">
                    <span
                      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold capitalize ${
                        job.status === 'parsed' || job.status === 'complete'
                          ? 'bg-mint-400/30 text-green-800'
                          : job.status?.includes('failed')
                          ? 'bg-red-100 text-red-800'
                          : 'bg-amber-100 text-amber-800'
                      }`}
                    >
                      <span
                        className={`w-1.5 h-1.5 rounded-full ${
                          job.status === 'parsed' || job.status === 'complete'
                            ? 'bg-mint-400/100'
                            : job.status?.includes('failed')
                            ? 'bg-red-500'
                            : 'bg-amber-500 animate-pulse'
                        }`}
                      ></span>
                      {job.status === 'complete' ? 'parsed' : job.status}
                    </span>
                  </td>
                  <td className="py-4 px-6 text-ash-400 text-xs">{formatRelativeTime(job.created_at)}</td>
                  <td className="py-4 px-8 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <a
                        href={`/api/admin/judgments/${job.pdf_id || job.job_id}/download`}
                        target="_blank"
                        rel="noopener noreferrer"
                        download={job.filename || "judgment.pdf"}
                        className="p-2 text-ash-400 hover:text-brand-600 transition-colors rounded-lg hover:bg-brand-50"
                        title="Download PDF from Drive"
                      >
                        <span className="material-symbols-outlined text-lg">download</span>
                      </a>
                      <button
                        onClick={() => setDeleteTarget(job)}
                        className="p-2 text-ash-400 hover:text-red-600 transition-colors rounded-lg hover:bg-red-50"
                        title="Delete Record"
                      >
                        <span className="material-symbols-outlined text-lg">delete</span>
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Controls Footer */}
      <AdminPagination
        currentPage={currentPage}
        totalPages={totalPages}
        onPageChange={setCurrentPage}
      />
    </div>
  );
};

export default RecentJobsTable;
