import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import AdminSidebar from '../components/AdminSidebar';
import AdminHeader from '../components/AdminHeader';
import AdminStatsCard from '../components/AdminStatsCard';
import AdminDeleteModal from '../components/AdminDeleteModal';
import IngestionProgress from '../components/IngestionProgress';
import RecentJobsTable from '../components/RecentJobsTable';

const AdminCasesPage = () => {
  const [currentAdmin, setCurrentAdmin] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    const storedAdmin = localStorage.getItem('currentAdmin');
    if (!storedAdmin) {
      navigate('/admin-login');
    } else {
      try {
        setCurrentAdmin(JSON.parse(storedAdmin));
      } catch (err) {
        console.error('Error parsing admin data:', err);
        navigate('/admin-login');
      }
    }
  }, [navigate]);

  const fileInputRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [uploadError, setUploadError] = useState('');
  const [recentJobs, setRecentJobs] = useState([]);
  const [recentLoading, setRecentLoading] = useState(true);
  const [recentError, setRecentError] = useState('');
  const [allJobs, setAllJobs] = useState([]);
  const [allJobsLoading, setAllJobsLoading] = useState(false);
  // fetchAllJobs reads and writes this, and the "All uploads" panel renders
  // it, but the state itself was never declared — so the fetch threw before
  // it could run.
  const [allJobsError, setAllJobsError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const JOBS_PER_PAGE = 6;
  const [showAllModal, setShowAllModal] = useState(false);
  const [deletingJobId, setDeletingJobId] = useState('');
  const [deleteTarget, setDeleteTarget] = useState(null);

  const [stats, setStats] = useState({ total_documents: 0, by_status: {} });
  const [activeJobId, setActiveJobId] = useState(null);
  const [activeJobStatus, setActiveJobStatus] = useState(null);
  const abortControllerRef = useRef(null);
  const [animatedProgress, setAnimatedProgress] = useState(0);

  const getStageStatus = (stageId) => {
    if (!activeJobStatus) return 'pending';
    const status = activeJobStatus.status;
    const statusSequence = ['verifying', 'uploaded', 'extracting', 'extracted', 'parsing', 'parsed'];
    const effectiveStatus = activeJobId === 'verifying' ? 'verifying' : status;
    const currentIdx = statusSequence.indexOf(effectiveStatus);
    const stageIdx = stageId - 1;

    if (status === 'extraction_failed') {
      if (stageIdx < 2) return 'completed';
      if (stageIdx === 2) return 'failed';
      return 'pending';
    }
    if (status === 'parse_failed') {
      if (stageIdx < 4) return 'completed';
      if (stageIdx === 4) return 'failed';
      return 'pending';
    }

    if (currentIdx < 0) return 'pending';
    if (currentIdx > stageIdx) return 'completed';
    if (currentIdx === stageIdx) return stageIdx === 5 ? 'completed' : 'active';
    return 'pending';
  };

  const stageRanges = {
    verifying: { start: 0, end: 5 },
    uploaded: { start: 5, end: 10 },
    extracting: { start: 10, end: 40 },
    extracted: { start: 40, end: 55 },
    parsing: { start: 55, end: 90 },
    parsed: { start: 90, end: 100 },
    extraction_failed: { start: 10, end: 40 },
    parse_failed: { start: 55, end: 90 },
  };

  useEffect(() => {
    if (!activeJobStatus) {
      setAnimatedProgress(0);
      return;
    }

    const effectiveStatus = activeJobId === 'verifying' ? 'verifying' : activeJobStatus.status;
    const range = stageRanges[effectiveStatus];
    if (!range) return;

    if (effectiveStatus === 'parsed') {
      setAnimatedProgress(100);
      return;
    }
    if (effectiveStatus === 'extraction_failed' || effectiveStatus === 'parse_failed') {
      setAnimatedProgress(range.end);
      return;
    }

    setAnimatedProgress(range.start);
    const ceiling = range.end - 1;
    let current = range.start;

    const interval = setInterval(() => {
      const remaining = ceiling - current;
      if (remaining <= 0.1) {
        clearInterval(interval);
        return;
      }
      current += Math.max(0.1, remaining * 0.08);
      setAnimatedProgress(Math.round(current));
    }, 200);

    return () => clearInterval(interval);
  }, [activeJobId, activeJobStatus?.status]);

  const handleCancelIngestion = async () => {
    const jobToCancel = activeJobId;
    if (!jobToCancel) return;

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    if (jobToCancel !== 'verifying') {
      try {
        await fetch(`/api/admin/jobs/${jobToCancel}`, { method: 'DELETE' });
      } catch (err) {
        console.error("Error cancelling job:", err);
      }
    }

    setActiveJobId(null);
    setActiveJobStatus(null);
    setUploading(false);
    fetchRecentJobs(false);
    fetchAllJobs();
  };

  const safeReadJson = async (response) => {
    const raw = await response.text();
    try {
      return raw ? JSON.parse(raw) : {};
    } catch {
      return {
        detail: "Backend returned non-JSON response. Check FastAPI server and Vite proxy target.",
      };
    }
  };

  const formatRelativeTime = (dateValue) => {
    if (!dateValue) return 'Unknown time';
    const date = new Date(dateValue);
    if (Number.isNaN(date.getTime())) return 'Unknown time';

    const diffMs = Date.now() - date.getTime();
    const diffMinutes = Math.floor(diffMs / 60000);
    if (diffMinutes < 1) return 'Just now';
    if (diffMinutes < 60) return `${diffMinutes} min${diffMinutes > 1 ? 's' : ''} ago`;

    const diffHours = Math.floor(diffMinutes / 60);
    if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;

    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
  };

  const fetchRecentJobs = async (showLoader = false) => {
    if (showLoader) setRecentLoading(true);
    setRecentError('');

    try {
      const response = await fetch('/api/admin/status');
      const data = await safeReadJson(response);
      if (!response.ok) {
        throw new Error(data?.detail || 'Failed to fetch recent uploads.');
      }
      const fetchedAll = Array.isArray(data?.all_jobs)
        ? data.all_jobs
        : Array.isArray(data?.recent_jobs)
        ? data.recent_jobs
        : [];
      setRecentJobs(Array.isArray(data?.recent_jobs) ? data.recent_jobs : fetchedAll);
      setAllJobs(fetchedAll);
      setStats({
        total_documents: data?.total_documents || 0,
        by_status: data?.by_status || {},
      });
    } catch (error) {
      setRecentError(error.message || 'Failed to fetch recent uploads.');
    } finally {
      if (showLoader) setRecentLoading(false);
    }
  };

  const fetchAllJobs = async () => {
    setAllJobsLoading(true);
    setAllJobsError('');
    try {
      const response = await fetch('/api/admin/jobs');
      const data = await safeReadJson(response);
      if (!response.ok) {
        throw new Error(data?.detail || 'Failed to fetch all uploads.');
      }
      if (Array.isArray(data?.jobs) && data.jobs.length > 0) {
        setAllJobs(data.jobs);
      }
    } catch (error) {
      setAllJobsError(error.message || 'Failed to fetch all uploads.');
    } finally {
      setAllJobsLoading(false);
    }
  };

  const openAllUploadsModal = async () => {
    setShowAllModal(true);
    await fetchAllJobs();
  };

  const parsedJobs = React.useMemo(() => {
    return allJobs.filter((job) => job.status === 'parsed' || job.status === 'complete');
  }, [allJobs]);

  const filteredJobs = React.useMemo(() => {
    if (!searchTerm.trim()) return parsedJobs;
    const term = searchTerm.toLowerCase().trim();
    return parsedJobs.filter((job) => {
      const matchFilename = (job.filename || '').toLowerCase().includes(term);
      const matchJobId = (job.job_id || '').toLowerCase().includes(term);
      return matchFilename || matchJobId;
    });
  }, [parsedJobs, searchTerm]);

  const totalPages = Math.ceil(filteredJobs.length / JOBS_PER_PAGE);
  const safeCurrentPage = Math.min(currentPage, Math.max(totalPages, 1));
  const startIndex = (safeCurrentPage - 1) * JOBS_PER_PAGE;
  const paginatedJobs = filteredJobs.slice(startIndex, startIndex + JOBS_PER_PAGE);

  useEffect(() => {
    fetchRecentJobs(true);
    fetchAllJobs();
    const intervalId = setInterval(() => {
      fetchRecentJobs(false);
      fetchAllJobs();
    }, 15000);

    return () => clearInterval(intervalId);
  }, []);

  useEffect(() => {
    if (!activeJobId || activeJobId === 'verifying') return;

    const terminalStates = ['parsed', 'complete', 'parse_failed', 'extraction_failed'];
    if (activeJobStatus && (activeJobStatus.status === 'parsed' || activeJobStatus.status === 'complete')) {
      setActiveJobId(null);
      setActiveJobStatus(null);
      setUploading(false);
      fetchRecentJobs(false);
      return;
    }

    let isSubscribed = true;
    const pollInterval = setInterval(async () => {
      try {
        const res = await fetch(`/api/admin/jobs/${activeJobId}`);
        if (res.ok) {
          const data = await res.json();
          if (isSubscribed) {
            setActiveJobStatus(data);
            if (data.status === 'parsed' || data.status === 'complete') {
              clearInterval(pollInterval);
              // Immediately remove the progress loading bar upon successful parse
              setActiveJobId(null);
              setActiveJobStatus(null);
              setUploading(false);
              fetchRecentJobs(false);
              fetchAllJobs();
            } else if (terminalStates.includes(data.status)) {
              clearInterval(pollInterval);
              setUploading(false);
              fetchRecentJobs(false);
              fetchAllJobs();
            }
          }
        } else {
          if (res.status === 404) {
            clearInterval(pollInterval);
            if (isSubscribed) {
              setActiveJobId(null);
              setActiveJobStatus(null);
              setUploading(false);
            }
          }
        }
      } catch (err) {
        console.error("Error polling job status:", err);
      }
    }, 1000);

    return () => {
      isSubscribed = false;
      clearInterval(pollInterval);
    };
  }, [activeJobId, activeJobStatus?.status]);

  const handlePickFile = () => {
    if (!uploading) {
      fileInputRef.current?.click();
    }
  };

  const handleFileSelected = async (event) => {
    const selectedFile = event.target.files?.[0];
    if (!selectedFile) return;

    setUploadError('');
    setUploadResult(null);

    if (!selectedFile.name.toLowerCase().endsWith('.pdf')) {
      setUploadError('Please select a PDF file.');
      event.target.value = '';
      return;
    }

    try {
      setUploading(true);
      setActiveJobId('verifying');
      setActiveJobStatus({
        status: 'verifying',
        filename: selectedFile.name,
      });

      const formData = new FormData();
      formData.append('file', selectedFile);

      abortControllerRef.current = new AbortController();
      const response = await fetch('/api/admin/upload', {
        method: 'POST',
        body: formData,
        signal: abortControllerRef.current.signal,
      });

      const raw = await response.text();
      let data = {};
      try {
        data = raw ? JSON.parse(raw) : {};
      } catch {
        data = {};
      }

      if (!response.ok) {
        if (response.status === 0 || response.status >= 500) {
          throw new Error('Backend is unreachable. Ensure FastAPI is running and Vite proxy target is correct.');
        }
        throw new Error(data?.detail || 'Upload failed.');
      }

      setUploadResult(data);
      setActiveJobId(data.job_id);
      setActiveJobStatus(data);
      fetchRecentJobs(false);
      if (showAllModal) fetchAllJobs();
    } catch (error) {
      if (error.name === 'AbortError') {
        return;
      }
      setUploadError(error.message || 'Upload failed.');
      setActiveJobId(null);
      setActiveJobStatus(null);
    } finally {
      setUploading(false);
      event.target.value = '';
    }
  };

  const handleDeleteJob = async (jobId) => {
    if (!jobId || deletingJobId) return;

    setDeletingJobId(jobId);
    setUploadError('');
    try {
      const response = await fetch(`/api/admin/jobs/${jobId}`, { method: 'DELETE' });
      const data = await safeReadJson(response);
      if (!response.ok) {
        throw new Error(data?.detail || 'Failed to delete case.');
      }
      await fetchRecentJobs(false);
      if (showAllModal) await fetchAllJobs();
    } catch (error) {
      setUploadError(error.message || 'Failed to delete case.');
    } finally {
      setDeletingJobId('');
    }
  };

  const confirmDeleteJob = async () => {
    if (!deleteTarget?.job_id) return;
    await handleDeleteJob(deleteTarget.job_id);
    setDeleteTarget(null);
  };

  return (
    <div className="flex min-h-screen bg-[#F8FAFC]">
      <AdminSidebar activeRoute="cases" currentAdmin={currentAdmin} />

      <main className="ml-72 flex-1 flex flex-col min-h-screen">
        <AdminHeader
          title="Case Document Ingestion"
          subtitle="Upload Supreme Court PDF judgments to process, extract, and index legal intelligence."
          actionButtonText="Upload New PDF"
          onActionClick={handlePickFile}
        />

        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,application/pdf"
          onChange={handleFileSelected}
          className="hidden"
        />

        <div className="p-12 flex flex-col gap-8 flex-1">
          {/* File Dropzone Header Banner */}
          <div className="bg-[#111827] rounded-2xl p-8 text-white relative overflow-hidden flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
            <div className="relative z-10 max-w-xl">
              <span className="inline-block px-3 py-1 bg-white/10 rounded-full text-xs font-semibold text-[#0085FF] uppercase tracking-wider mb-3">
                Automated Pipeline
              </span>
              <h2 className="font-display font-bold text-2xl mb-2">Drag & Drop Judgment Documents</h2>
              <p className="font-prose text-sm text-[#6B7280]">
                PDF documents undergo multi-stage text extraction, chunking, vector embedding, and database ingestion.
              </p>
            </div>
            <div className="relative z-10 flex items-center gap-3">
              {activeJobId && (
                <button
                  onClick={handleCancelIngestion}
                  className="bg-red-500/20 text-red-300 hover:bg-red-500/30 border border-red-400/30 px-5 py-3.5 rounded-xl font-prose font-bold text-sm transition-all flex items-center gap-2"
                >
                  <span className="material-symbols-outlined text-lg">close</span>
                  Cancel Ingestion
                </button>
              )}
              <button
                onClick={handlePickFile}
                disabled={uploading}
                className="grad-btn flex items-center gap-2 rounded-xl px-6 py-3.5 font-ui text-sm font-bold text-white shadow-glow transition-all duration-300 hover:-translate-y-0.5 hover:shadow-glow-lg disabled:opacity-50 disabled:translate-y-0 disabled:shadow-none"
              >
                <span className="material-symbols-outlined text-lg">upload_file</span>
                {uploading ? 'Processing Ingestion...' : 'Select PDF File'}
              </button>
            </div>
          </div>

          {uploadError && (
            <div className="bg-red-50 text-red-700 p-4 rounded-xl text-xs font-prose border border-red-100 flex items-center gap-2">
              <span className="material-symbols-outlined text-red-600">error</span>
              {uploadError}
            </div>
          )}

          {/* Progress Section */}
          <IngestionProgress
            activeJobId={activeJobId}
            activeJobStatus={activeJobStatus}
            animatedProgress={animatedProgress}
            getStageStatus={getStageStatus}
            handleCancelIngestion={handleCancelIngestion}
          />

          {/* Stats Overview */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <AdminStatsCard
              label="Total Processed"
              value={stats.total_documents}
              subtext="documents in vector index"
              icon="description"
              loading={recentLoading}
            />
            <AdminStatsCard
              label="Parsed Successfully"
              value={(stats.by_status?.parsed || 0) + (stats.by_status?.complete || 0)}
              subtext="fully indexed judgments"
              icon="task_alt"
              loading={recentLoading}
            />
            <AdminStatsCard
              label="Failed / Processing"
              value={(stats.by_status?.failed || 0) + (stats.by_status?.processing || 0)}
              subtext="in-flight or error states"
              icon="pending"
              loading={recentLoading}
            />
          </div>

          {/* Case Ingestion History Table with Search & Pagination */}
          <RecentJobsTable
            recentLoading={recentLoading}
            recentError={recentError}
            allJobs={parsedJobs}
            filteredJobs={filteredJobs}
            paginatedJobs={paginatedJobs}
            searchTerm={searchTerm}
            setSearchTerm={setSearchTerm}
            currentPage={safeCurrentPage}
            setCurrentPage={setCurrentPage}
            totalPages={totalPages}
            formatRelativeTime={formatRelativeTime}
            setShowAllModal={openAllUploadsModal}
            setDeleteTarget={setDeleteTarget}
          />
        </div>
      </main>

      {/* Delete Modal */}
      <AdminDeleteModal
        isOpen={!!deleteTarget}
        title="Delete Judgment Document"
        message={`Are you sure you want to delete "${deleteTarget?.filename}"? This action removes all extracted vectors and text indices.`}
        onConfirm={confirmDeleteJob}
        onCancel={() => setDeleteTarget(null)}
      />

      {/* View All Modal */}
      {showAllModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-[100] animate-fade-in">
          <div className="bg-white rounded-2xl w-full max-w-4xl max-h-[85vh] overflow-y-auto p-8 shadow-2xl relative border border-ash-100 flex flex-col gap-6">
            <div className="flex justify-between items-center">
              <div>
                <h3 className="font-display font-bold text-2xl text-[#111827]">Complete Case History</h3>
                <p className="font-prose text-xs text-ash-500 mt-1">All uploaded PDF judgments and their ingestion states.</p>
              </div>
              <button
                onClick={() => setShowAllModal(false)}
                className="text-ash-400 hover:text-ash-600 transition-colors"
              >
                <span className="material-symbols-outlined text-2xl">close</span>
              </button>
            </div>

            {allJobsError && (
              <div role="alert" className="flex items-start gap-2.5 bg-red-50 text-red-700 p-4 rounded-xl text-xs font-prose">
                <span className="material-symbols-outlined shrink-0 text-base leading-5" aria-hidden="true">
                  error
                </span>
                <span>{allJobsError}</span>
              </div>
            )}

            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse font-prose text-sm">
                <thead>
                  <tr className="border-b border-ash-100 text-xs font-bold text-ash-400 uppercase tracking-wider">
                    <th className="py-3 px-4">Filename</th>
                    <th className="py-3 px-4">Job ID</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Uploaded</th>
                    <th className="py-3 px-4 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ash-50">
                  {allJobsLoading ? (
                    <tr>
                      <td colSpan="5" className="py-8 text-center text-ash-400">Loading history...</td>
                    </tr>
                  ) : allJobs.length === 0 ? (
                    <tr>
                      <td colSpan="5" className="py-8 text-center text-ash-400">No uploads found.</td>
                    </tr>
                  ) : (
                    allJobs.map((job) => (
                      <tr key={job.job_id} className="hover:bg-ash-50">
                        <td className="py-3.5 px-4 font-medium text-[#111827]">{job.filename || 'Unnamed'}</td>
                        <td className="py-3.5 px-4 font-mono text-xs text-ash-500">{job.job_id}</td>
                        <td className="py-3.5 px-4">
                          <span className="capitalize text-xs font-semibold px-2.5 py-1 rounded-full bg-ash-100 text-ash-700">
                            {job.status}
                          </span>
                        </td>
                        <td className="py-3.5 px-4 text-xs text-ash-400">{formatRelativeTime(job.created_at)}</td>
                        <td className="py-3.5 px-4 text-right">
                          <button
                            onClick={() => {
                              setShowAllModal(false);
                              setDeleteTarget(job);
                            }}
                            className="text-red-600 hover:text-red-800 text-xs font-bold"
                          >
                            Delete
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminCasesPage;
