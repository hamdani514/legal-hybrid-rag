import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import AdminSidebar from '../components/AdminSidebar';
import AdminHeader from '../components/AdminHeader';
import AdminStatsCard from '../components/AdminStatsCard';
import AdminDeleteModal from '../components/AdminDeleteModal';
import IngestionProgress from '../components/IngestionProgress';
import AdminPagination from '../components/AdminPagination';
import UploadQueue, { isTerminalJob } from '../components/UploadQueue';
import { apiFetch, ADMIN_TOKEN_KEY } from '../../lib/api';

// Files uploaded at the same time from the browser. The server queues them
// anyway (ADMIN_INGEST_CONCURRENCY); this only bounds the upload requests.
const UPLOAD_PARALLEL = 2;
const QUEUE_POLL_MS = 2500;

/*
 * Case ingestion console.
 *
 * A judgment is findable only once several stores are written (tree, dense
 * vectors, keyword index; then its case card and card vector). The backend
 * records each one on index_status and derives the document status from it:
 *   searchable  every store search needs is written; the case card may follow
 *   complete    searchable + card + card vector
 *   failed      a stage failed (the job status names it: parse_failed,
 *               embedding_failed, ...) — Retry resumes from the last good store
 * Earlier this page treated "parsed" as done and hid everything else, so a
 * judgment that never reached the search index looked finished and a failed
 * upload was invisible. Every job is listed with its state, who uploaded it,
 * when, and a Retry button. (The per-store and parse-quality columns were
 * dropped from this table; the state pill and the backend check still carry
 * that detail.)
 */

const DONE_STATUSES = ['searchable', 'complete'];
const IN_FLIGHT = ['uploaded', 'queued', 'extracting', 'extracted', 'parsing', 'parsed', 'tree', 'embedding', 'indexing'];
const STALL_MINUTES = 15;

const isFailed = (job) => (job.status || '').endsWith('_failed') || job.doc_status === 'failed' || job.status === 'failed';

const isStalled = (job) => {
  if (!IN_FLIGHT.includes(job.status)) return false;
  // The server still has a task for it: waiting in the upload queue or running.
  if (job.active) return false;
  const stamp = new Date(job.updated_at || job.created_at || 0).getTime();
  return Number.isFinite(stamp) && Date.now() - stamp > STALL_MINUTES * 60000;
};

// One user-facing state per job: complete | searchable | failed | stalled | processing
const caseState = (job) => {
  if (isFailed(job)) return 'failed';
  const s = job.doc_status || job.status;
  if (s === 'complete' || s === 'searchable') return s;
  if (isStalled(job)) return 'stalled';
  return 'processing';
};

const STATE_STYLE = {
  complete: { pill: 'bg-mint-400/30 text-green-800', dot: 'bg-mint-400/100', label: 'complete' },
  searchable: { pill: 'bg-brand-50 text-brand-600', dot: 'bg-brand-600', label: 'searchable' },
  failed: { pill: 'bg-red-100 text-red-800', dot: 'bg-red-500', label: 'failed' },
  stalled: { pill: 'bg-amber-100 text-amber-800', dot: 'bg-amber-500', label: 'stalled' },
  processing: { pill: 'bg-amber-100 text-amber-800', dot: 'bg-amber-500 animate-pulse', label: 'processing' },
};

const readAdminToken = () => {
  try {
    return localStorage.getItem(ADMIN_TOKEN_KEY) || '';
  } catch {
    return '';
  }
};

const adminDownloadUrl = (job) => {
  const base = `/api/admin/judgments/${job.pdf_id || job.job_id}/download`;
  const token = readAdminToken();
  // An <a href> cannot send an Authorization header; the route accepts ?token=.
  return token ? `${base}?token=${encodeURIComponent(token)}` : base;
};

const StatePill = ({ job }) => {
  const state = caseState(job);
  const style = STATE_STYLE[state];
  const detail = state === 'processing' ? job.status : state === 'failed' ? (job.status || '').replace('_', ' ') : style.label;
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold capitalize ${style.pill}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${style.dot}`}></span>
      {detail}
    </span>
  );
};

const errorText = (job) => job.error || job.index_status?.last_error || '';

const canRetry = (job) => {
  const state = caseState(job);
  return state === 'failed' || state === 'stalled' || state === 'searchable';
};

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
  const [uploadNotice, setUploadNotice] = useState('');
  const [recentLoading, setRecentLoading] = useState(true);
  const [recentError, setRecentError] = useState('');
  const [allJobs, setAllJobs] = useState([]);
  const [allJobsLoading, setAllJobsLoading] = useState(false);
  const [allJobsError, setAllJobsError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [sortOrder, setSortOrder] = useState('newest');
  const [currentPage, setCurrentPage] = useState(1);
  const JOBS_PER_PAGE = 6;
  const [showAllModal, setShowAllModal] = useState(false);
  const [deletingJobId, setDeletingJobId] = useState('');
  const [retryingJobId, setRetryingJobId] = useState('');
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [selectedJobIds, setSelectedJobIds] = useState([]);
  const [batchDeleting, setBatchDeleting] = useState(false);
  const [showBatchDeleteModal, setShowBatchDeleteModal] = useState(false);

  const [stats, setStats] = useState({ total_documents: 0, by_status: {} });
  const [activeJobId, setActiveJobId] = useState(null);
  const [activeJobStatus, setActiveJobStatus] = useState(null);
  const abortControllerRef = useRef(null);
  const [animatedProgress, setAnimatedProgress] = useState(0);

  const getStageStatus = (stageId) => {
    if (!activeJobStatus) return 'pending';
    const status = activeJobStatus.status;
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
    // Failures after the parse (tree, vectors, keyword index) fail the last stage.
    if (['tree_failed', 'embedding_failed', 'index_failed'].includes(status)) {
      return stageIdx < 5 ? 'completed' : 'failed';
    }
    if (DONE_STATUSES.includes(status)) return 'completed';

    // The last stage covers parse -> searchable: tree, embedding, indexing.
    const statusSequence = ['verifying', 'uploaded', 'extracting', 'extracted', 'parsing', 'parsed'];
    const normalised =
      activeJobId === 'verifying'
        ? 'verifying'
        : status === 'queued'
        ? 'uploaded'
        : ['tree', 'embedding', 'indexing'].includes(status)
        ? 'parsed'
        : status;
    const currentIdx = statusSequence.indexOf(normalised);
    if (currentIdx < 0) return 'pending';
    if (currentIdx > stageIdx) return 'completed';
    if (currentIdx === stageIdx) return 'active';
    return 'pending';
  };

  const stageRanges = {
    verifying: { start: 0, end: 5 },
    uploaded: { start: 5, end: 10 },
    queued: { start: 5, end: 10 },
    extracting: { start: 10, end: 40 },
    extracted: { start: 40, end: 55 },
    parsing: { start: 55, end: 80 },
    parsed: { start: 80, end: 85 },
    tree: { start: 85, end: 88 },
    embedding: { start: 88, end: 99 },
    indexing: { start: 88, end: 99 },
    searchable: { start: 100, end: 100 },
    complete: { start: 100, end: 100 },
    extraction_failed: { start: 10, end: 40 },
    parse_failed: { start: 55, end: 80 },
    tree_failed: { start: 85, end: 88 },
    embedding_failed: { start: 88, end: 99 },
    index_failed: { start: 88, end: 99 },
  };

  useEffect(() => {
    if (!activeJobStatus) {
      setAnimatedProgress(0);
      return;
    }

    const effectiveStatus = activeJobId === 'verifying' ? 'verifying' : activeJobStatus.status;
    const range = stageRanges[effectiveStatus];
    if (!range) return;

    if (DONE_STATUSES.includes(effectiveStatus)) {
      setAnimatedProgress(100);
      return;
    }
    if ((effectiveStatus || '').endsWith('_failed')) {
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
        await apiFetch(`/api/admin/jobs/${jobToCancel}`, { method: 'DELETE' });
      } catch (err) {
        console.error('Error cancelling job:', err);
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
        detail: 'Backend returned non-JSON response. Check FastAPI server and Vite proxy target.',
      };
    }
  };

  const formatRelativeTime = (dateValue) => {
    if (!dateValue) return 'Unknown time';
    // The backend stores UTC but serialises it without a 'Z' (e.g.
    // "2026-10-05T07:48:06"); the browser would otherwise read that as local
    // time and show a fresh upload as "5 hours ago". Treat a bare timestamp
    // as UTC so the elapsed time is correct.
    const needsZ = typeof dateValue === 'string' && !/[zZ]|[+-]\d{2}:?\d{2}$/.test(dateValue);
    const date = new Date(needsZ ? `${dateValue}Z` : dateValue);
    if (Number.isNaN(date.getTime())) return 'Unknown time';

    const diffSeconds = Math.round((Date.now() - date.getTime()) / 1000);
    if (diffSeconds < 5) return 'Just now';
    if (diffSeconds < 60) return `${diffSeconds} sec${diffSeconds === 1 ? '' : 's'} ago`;

    const diffMinutes = Math.floor(diffSeconds / 60);
    if (diffMinutes < 60) return `${diffMinutes} min${diffMinutes > 1 ? 's' : ''} ago`;

    const diffHours = Math.floor(diffMinutes / 60);
    if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;

    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
  };

  // The admin who uploaded a case, for the "Uploaded by" column.
  const uploaderLabel = (job) => {
    const by = job.uploaded_by;
    if (!by) return '—';
    if (typeof by === 'string') return by;
    return by.name || by.id || '—';
  };

  // Tag every upload with the signed-in admin (auth is off, so the server
  // cannot derive it yet); shown back in the "Uploaded by" column.
  const appendUploader = (formData) => {
    formData.append('uploaded_by', currentAdmin?.name || '');
    formData.append('uploaded_by_id', currentAdmin?.adminid || currentAdmin?.email || '');
  };

  const fetchRecentJobs = async (showLoader = false) => {
    if (showLoader) setRecentLoading(true);
    setRecentError('');

    try {
      const response = await apiFetch('/api/admin/status');
      const data = await safeReadJson(response);
      if (!response.ok) {
        throw new Error(data?.detail || 'Failed to fetch recent uploads.');
      }
      const fetchedAll = Array.isArray(data?.all_jobs)
        ? data.all_jobs
        : Array.isArray(data?.recent_jobs)
        ? data.recent_jobs
        : [];
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
      const response = await apiFetch('/api/admin/jobs');
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

  // Counts by user-facing state, from the jobs themselves (the status endpoint
  // predates the searchable/complete split).
  const stateCounts = React.useMemo(() => {
    const counts = { complete: 0, searchable: 0, failed: 0, stalled: 0, processing: 0, flagged: 0 };
    allJobs.forEach((job) => {
      counts[caseState(job)] += 1;
      if (job.quality_passed === false) counts.flagged += 1;
    });
    return counts;
  }, [allJobs]);

  const filteredJobs = React.useMemo(() => {
    const term = searchTerm.toLowerCase().trim();
    const jobs = allJobs.filter((job) => {
      if (!term) return true;
      return (job.filename || '').toLowerCase().includes(term) || (job.job_id || '').toLowerCase().includes(term);
    });
    return [...jobs].sort((a, b) => {
      const dateA = new Date(a.created_at || 0).getTime();
      const dateB = new Date(b.created_at || 0).getTime();
      return sortOrder === 'oldest' ? dateA - dateB : dateB - dateA;
    });
  }, [allJobs, searchTerm, sortOrder]);

  const sortedAllJobs = React.useMemo(() => {
    return [...allJobs].sort((a, b) => {
      const dateA = new Date(a.created_at || 0).getTime();
      const dateB = new Date(b.created_at || 0).getTime();
      return sortOrder === 'oldest' ? dateA - dateB : dateB - dateA;
    });
  }, [allJobs, sortOrder]);

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

    const finish = () => {
      setActiveJobId(null);
      setActiveJobStatus(null);
      setUploading(false);
      fetchRecentJobs(false);
      fetchAllJobs();
    };

    if (activeJobStatus && DONE_STATUSES.includes(activeJobStatus.status)) {
      finish();
      return;
    }

    let isSubscribed = true;
    const pollInterval = setInterval(async () => {
      try {
        const res = await apiFetch(`/api/admin/jobs/${activeJobId}`);
        if (res.ok) {
          const data = await res.json();
          if (isSubscribed) {
            setActiveJobStatus(data);
            if (DONE_STATUSES.includes(data.status)) {
              clearInterval(pollInterval);
              finish();
            } else if ((data.status || '').endsWith('_failed')) {
              clearInterval(pollInterval);
              setUploading(false);
              fetchRecentJobs(false);
              fetchAllJobs();
            }
          }
        } else if (res.status === 404) {
          clearInterval(pollInterval);
          if (isSubscribed) {
            setActiveJobId(null);
            setActiveJobStatus(null);
            setUploading(false);
          }
        }
      } catch (err) {
        console.error('Error polling job status:', err);
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

  // ── Several files at once ────────────────────────────────────────────────
  // Every file is its own POST /api/admin/upload and its own judgment. The
  // browser sends UPLOAD_PARALLEL at a time; the server queues their
  // ingestion. Rows are tracked with POST /api/admin/jobs/lookup.
  const [queue, setQueue] = useState([]);
  const [pollTick, setPollTick] = useState(0);
  const [dragOver, setDragOver] = useState(false);
  const queueFilesRef = useRef(new Map()); // row key -> File, until uploaded
  const startedRef = useRef(new Set());

  const updateRow = (key, fields) =>
    setQueue((rows) => rows.map((row) => (row.key === key ? { ...row, ...fields } : row)));

  const addToQueue = (files) => {
    const rows = files.map((file, i) => {
      const key = `${Date.now()}-${i}-${file.name}`;
      const isPdf = file.name.toLowerCase().endsWith('.pdf');
      if (isPdf) queueFilesRef.current.set(key, file);
      return {
        key,
        name: file.name,
        size: file.size,
        state: isPdf ? 'waiting' : 'rejected',
        error: isPdf ? '' : 'Not a PDF file.',
      };
    });
    setQueue((existing) => [...existing, ...rows]);
  };

  const uploadQueued = async (row) => {
    const file = queueFilesRef.current.get(row.key);
    if (!file) {
      updateRow(row.key, { state: 'cancelled' });
      return;
    }
    updateRow(row.key, { state: 'uploading' });
    try {
      const formData = new FormData();
      formData.append('file', file);
      appendUploader(formData);
      const response = await apiFetch('/api/admin/upload', { method: 'POST', body: formData });
      const data = await safeReadJson(response);
      if (!response.ok) {
        updateRow(row.key, {
          state: 'rejected',
          error:
            response.status >= 500
              ? 'The server could not process this file. Check that the backend is running.'
              : data?.detail || `Upload failed (${response.status}).`,
        });
      } else {
        updateRow(row.key, {
          state: 'tracking',
          jobId: data.job_id,
          status: data.status || 'uploaded',
          active: true,
          notice: data.resumed ? data.message : '',
        });
      }
    } catch (error) {
      updateRow(row.key, { state: 'rejected', error: 'Could not reach the server.' });
    } finally {
      queueFilesRef.current.delete(row.key);
    }
  };

  // Scheduler: keep UPLOAD_PARALLEL uploads in flight while files wait.
  useEffect(() => {
    const inFlight = queue.filter((row) => row.state === 'uploading').length;
    const free = UPLOAD_PARALLEL - inFlight;
    if (free <= 0) return;
    queue
      .filter((row) => row.state === 'waiting' && !startedRef.current.has(row.key))
      .slice(0, free)
      .forEach((row) => {
        startedRef.current.add(row.key);
        uploadQueued(row);
      });
  }, [queue]);

  // Poll the server for the batch's jobs until each one is finished.
  useEffect(() => {
    const open = queue.filter((row) => row.state === 'tracking' && !isTerminalJob(row.status) && row.active !== false);
    if (!open.length) return undefined;
    const timer = setTimeout(async () => {
      try {
        const response = await apiFetch('/api/admin/jobs/lookup', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ job_ids: open.map((row) => row.jobId) }),
        });
        const data = await safeReadJson(response);
        if (response.ok && Array.isArray(data?.jobs)) {
          const byId = new Map(data.jobs.map((job) => [job.job_id, job]));
          let finishedNow = false;
          setQueue((rows) =>
            rows.map((row) => {
              if (row.state !== 'tracking' || !open.some((o) => o.key === row.key)) return row;
              const job = byId.get(row.jobId);
              if (!job) return { ...row, state: 'removed' };
              if (isTerminalJob(job.status) && !isTerminalJob(row.status)) finishedNow = true;
              return { ...row, status: job.status, active: job.active, error: job.error || row.error };
            })
          );
          if (finishedNow) fetchRecentJobs(false);
        }
      } catch (error) {
        console.error('Error polling batch status:', error);
      } finally {
        setPollTick((t) => t + 1);
      }
    }, QUEUE_POLL_MS);
    return () => clearTimeout(timer);
  }, [queue, pollTick]);

  // Files still in the browser are lost if the page closes: warn first.
  useEffect(() => {
    const pending = queue.some((row) => row.state === 'waiting' || row.state === 'uploading');
    if (!pending) return undefined;
    const warn = (e) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [queue]);

  const cancelWaiting = () => {
    setQueue((rows) =>
      rows.map((row) => {
        if (row.state !== 'waiting') return row;
        queueFilesRef.current.delete(row.key);
        return { ...row, state: 'cancelled' };
      })
    );
  };

  const clearFinished = () => {
    setQueue((rows) =>
      rows.filter(
        (row) =>
          !(
            ['rejected', 'cancelled', 'removed'].includes(row.state) ||
            (row.state === 'tracking' && (isTerminalJob(row.status) || row.active === false))
          )
      )
    );
    fetchRecentJobs(false);
  };

  const batchBusy = queue.some(
    (row) =>
      row.state === 'waiting' ||
      row.state === 'uploading' ||
      (row.state === 'tracking' && !isTerminalJob(row.status) && row.active !== false)
  );

  // One file with nothing else running keeps the detailed single-file view;
  // several files (or more files while a batch runs) go to the queue.
  const routeFiles = (fileList) => {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    setUploadError('');
    setUploadNotice('');
    if (files.length === 1 && !batchBusy && !queue.length && !activeJobId) {
      uploadSingle(files[0]);
    } else {
      addToQueue(files);
    }
  };

  const handleFileSelected = (event) => {
    routeFiles(event.target.files);
    event.target.value = '';
  };

  const handleDrop = (event) => {
    event.preventDefault();
    setDragOver(false);
    routeFiles(event.dataTransfer?.files);
  };

  const uploadSingle = async (selectedFile) => {
    setUploadResult(null);

    if (!selectedFile.name.toLowerCase().endsWith('.pdf')) {
      setUploadError('Please select a PDF file.');
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
      appendUploader(formData);

      abortControllerRef.current = new AbortController();
      const response = await apiFetch('/api/admin/upload', {
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

      // Re-uploading a PDF that failed before resumes that record.
      if (data.resumed) setUploadNotice(data.message || 'Resuming the earlier upload of this PDF.');
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
    }
  };

  const handleRetryJob = async (job) => {
    const jobId = job?.job_id || job?.pdf_id;
    if (!jobId || retryingJobId) return;
    setRetryingJobId(jobId);
    setUploadError('');
    setUploadNotice('');
    try {
      const response = await apiFetch(`/api/admin/jobs/${jobId}/retry`, { method: 'POST' });
      const data = await safeReadJson(response);
      if (!response.ok) {
        throw new Error(data?.detail || 'Retry failed.');
      }
      setUploadNotice(`${job.filename || jobId}: ${data.message || 'retry started.'}`);
      if (data.status === 'queued') {
        setActiveJobId(jobId);
        setActiveJobStatus({ ...data, filename: job.filename });
      }
      await fetchRecentJobs(false);
      if (showAllModal) await fetchAllJobs();
    } catch (error) {
      setUploadError(error.message || 'Retry failed.');
    } finally {
      setRetryingJobId('');
    }
  };

  const handleDeleteJob = async (jobId) => {
    if (!jobId || deletingJobId) return;

    setDeletingJobId(jobId);
    setUploadError('');
    try {
      const response = await apiFetch(`/api/admin/jobs/${jobId}`, { method: 'DELETE' });
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

  const toggleSelectJob = (jobId) => {
    if (!jobId) return;
    setSelectedJobIds((prev) =>
      prev.includes(jobId) ? prev.filter((id) => id !== jobId) : [...prev, jobId]
    );
  };

  const handleSelectAll = (items) => {
    const itemIds = (items || []).map((j) => j.job_id).filter(Boolean);
    const allSelected = itemIds.length > 0 && itemIds.every((id) => selectedJobIds.includes(id));
    if (allSelected) {
      setSelectedJobIds((prev) => prev.filter((id) => !itemIds.includes(id)));
    } else {
      setSelectedJobIds((prev) => Array.from(new Set([...prev, ...itemIds])));
    }
  };

  const clearSelection = () => {
    setSelectedJobIds([]);
  };

  const confirmBatchDelete = async () => {
    if (!selectedJobIds.length || batchDeleting) return;

    setBatchDeleting(true);
    setUploadError('');
    try {
      const response = await apiFetch('/api/admin/jobs/batch-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_ids: selectedJobIds }),
      });
      const data = await safeReadJson(response);
      if (!response.ok) {
        throw new Error(data?.detail || 'Failed to delete selected cases.');
      }
      setUploadNotice(`Successfully deleted ${data.deleted_count ?? selectedJobIds.length} case(s).`);
      setSelectedJobIds([]);
      setShowBatchDeleteModal(false);
      await fetchRecentJobs(false);
      if (showAllModal) await fetchAllJobs();
    } catch (error) {
      setUploadError(error.message || 'Failed to delete selected cases.');
    } finally {
      setBatchDeleting(false);
    }
  };

  const RowActions = ({ job, onDelete }) => (
    <div className="flex items-center justify-end gap-1">
      {canRetry(job) && (
        <button
          onClick={() => handleRetryJob(job)}
          disabled={!!retryingJobId}
          className="px-2.5 py-1.5 text-xs font-bold text-brand-600 hover:text-brand-800 rounded-lg hover:bg-brand-50 transition-colors inline-flex items-center gap-1 disabled:opacity-50"
          title={
            caseState(job) === 'searchable'
              ? 'Build the missing case card (one AI call)'
              : 'Resume from the last stage that succeeded'
          }
        >
          <span className="material-symbols-outlined text-base">refresh</span>
          {retryingJobId === (job.job_id || job.pdf_id) ? 'Retrying...' : caseState(job) === 'searchable' ? 'Card' : 'Retry'}
        </button>
      )}
      <a
        href={adminDownloadUrl(job)}
        target="_blank"
        rel="noopener noreferrer"
        download={job.filename || 'judgment.pdf'}
        className="p-2 text-ash-400 hover:text-brand-600 transition-colors rounded-lg hover:bg-brand-50"
        title="Download PDF"
      >
        <span className="material-symbols-outlined text-lg">download</span>
      </a>
      <button
        onClick={() => onDelete(job)}
        className="p-2 text-ash-400 hover:text-red-600 transition-colors rounded-lg hover:bg-red-50"
        title="Delete Record"
      >
        <span className="material-symbols-outlined text-lg">delete</span>
      </button>
    </div>
  );



  return (
    <div className="flex min-h-screen bg-[#F8FAFC]">
      <AdminSidebar activeRoute="cases" currentAdmin={currentAdmin} />

      <main className="ml-72 flex-1 flex flex-col min-h-screen">
        <AdminHeader
          title="Case Document Ingestion"
          subtitle="Upload Supreme Court PDF judgments to process, extract, and index legal intelligence."
          actionButtonText="Upload PDFs"
          onActionClick={handlePickFile}
        />

        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,application/pdf"
          multiple
          onChange={handleFileSelected}
          className="hidden"
        />

        <div className="p-12 flex flex-col gap-8 flex-1">
          {/* File Dropzone Header Banner */}
          <div
            onDragOver={(e) => {
              e.preventDefault();
              if (!dragOver) setDragOver(true);
            }}
            onDragLeave={(e) => {
              if (!e.currentTarget.contains(e.relatedTarget)) setDragOver(false);
            }}
            onDrop={handleDrop}
            className={`bg-[#111827] rounded-2xl p-8 text-white relative overflow-hidden flex flex-col md:flex-row justify-between items-start md:items-center gap-6 transition-shadow ${
              dragOver ? 'ring-4 ring-[#0085FF]/60' : ''
            }`}
          >
            <div className="relative z-10 max-w-xl">
              <span className="inline-block px-3 py-1 bg-white/10 rounded-full text-xs font-semibold text-[#0085FF] uppercase tracking-wider mb-3">
                Automated Pipeline
              </span>
              <h2 className="font-display font-bold text-2xl mb-2">
                {dragOver ? 'Drop the PDFs to upload them' : 'Drag & Drop Judgment Documents'}
              </h2>
              <p className="font-prose text-sm text-[#6B7280]">
                Select or drop one PDF or many. Each judgment goes through text extraction, parsing, vector embedding
                and indexing on its own.
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
                {uploading ? 'Processing Ingestion...' : batchBusy ? 'Add More PDFs' : 'Select PDF Files'}
              </button>
            </div>
          </div>

          {uploadError && (
            <div className="bg-red-50 text-red-700 p-4 rounded-xl text-xs font-prose border border-red-100 flex items-center gap-2">
              <span className="material-symbols-outlined text-red-600">error</span>
              {uploadError}
            </div>
          )}
          {uploadNotice && !uploadError && (
            <div className="bg-brand-50 text-brand-600 p-4 rounded-xl text-xs font-prose border border-brand-100 flex items-center gap-2">
              <span className="material-symbols-outlined">info</span>
              {uploadNotice}
            </div>
          )}

          {/* Several files: one row per judgment */}
          <UploadQueue queue={queue} onCancelWaiting={cancelWaiting} onClearFinished={clearFinished} />

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
              subtext="judgment records"
              icon="description"
              loading={recentLoading}
            />
            <AdminStatsCard
              label="Searchable"
              value={stateCounts.searchable + stateCounts.complete}
              subtext={`${stateCounts.complete} complete with case card`}
              icon="task_alt"
              tone="good"
              loading={recentLoading}
            />
            <AdminStatsCard
              label="Failed / Processing"
              value={stateCounts.failed + stateCounts.stalled + stateCounts.processing}
              subtext={`${stateCounts.failed} failed, ${stateCounts.stalled} stalled, ${stateCounts.flagged} parses flagged`}
              icon="pending"
              tone={stateCounts.failed + stateCounts.stalled > 0 ? 'bad' : 'neutral'}
              loading={recentLoading}
            />
          </div>

          {/* Case Ingestion History: every job, with its stores, quality and actions */}
          <div className="flex flex-col overflow-hidden rounded-3xl border border-ash-200 bg-white shadow-soft">
            <div className="p-8 pb-6 border-b border-ash-100 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
              <div>
                <h3 className="font-display font-bold text-xl text-[#111827]">Case Ingestion History</h3>
                <p className="font-prose text-xs text-ash-500 mt-1">
                  Searchable = vectors and keyword index written; complete = its case card too.
                </p>
              </div>
              <div className="flex items-center gap-3 w-full md:w-auto">
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
                <button
                  onClick={openAllUploadsModal}
                  className="text-xs font-bold text-brand-600 hover:text-brand-800 whitespace-nowrap"
                >
                  View all
                </button>
              </div>
            </div>

            <div className="px-8 py-3 bg-[#F8FAFC] border-b border-ash-100 flex flex-wrap gap-3 items-center justify-between text-xs font-prose">
              <div className="flex items-center gap-2.5">
                <span className="text-ash-500 font-medium flex items-center gap-1">
                  <span className="material-symbols-outlined text-[16px] text-ash-400">swap_vert</span>
                  Sort:
                </span>
                <div className="inline-flex p-0.5 bg-white border border-ash-200 rounded-lg shadow-2xs">
                  <button
                    type="button"
                    onClick={() => {
                      setSortOrder('newest');
                      setCurrentPage(1);
                    }}
                    className={`px-3 py-1 rounded-md text-xs font-semibold transition-all ${
                      sortOrder === 'newest'
                        ? 'bg-[#111827] text-white shadow-2xs'
                        : 'text-ash-500 hover:text-[#111827]'
                    }`}
                  >
                    Newest
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setSortOrder('oldest');
                      setCurrentPage(1);
                    }}
                    className={`px-3 py-1 rounded-md text-xs font-semibold transition-all ${
                      sortOrder === 'oldest'
                        ? 'bg-[#111827] text-white shadow-2xs'
                        : 'text-ash-500 hover:text-[#111827]'
                    }`}
                  >
                    Oldest
                  </button>
                </div>
              </div>
              <span className="text-[#6B7280]">
                Showing {paginatedJobs.length} of {filteredJobs.length}
              </span>
            </div>

            {recentError && (
              <div role="alert" className="flex items-start gap-2.5 mx-8 mt-4 bg-red-50 text-red-700 p-4 rounded-xl text-xs font-prose">
                <span className="material-symbols-outlined shrink-0 text-base leading-5" aria-hidden="true">error</span>
                <span>{recentError}</span>
              </div>
            )}

            {/* Main Table Bulk Action Bar - Clean, No Background Highlight */}
            {selectedJobIds.length > 0 && (
              <div className="px-8 py-3 bg-white border-b border-ash-100 flex items-center justify-between text-xs font-prose animate-fade-in">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-[#0085FF]" />
                  <span className="font-semibold text-sm text-[#111827]">
                    {selectedJobIds.length} case{selectedJobIds.length > 1 ? 's' : ''} selected
                  </span>
                </div>
                <div className="flex items-center gap-4">
                  <button
                    type="button"
                    onClick={clearSelection}
                    className="text-xs font-medium text-ash-500 hover:text-[#111827] transition-colors"
                  >
                    Clear all
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowBatchDeleteModal(true)}
                    disabled={batchDeleting}
                    className="px-3.5 py-1.5 bg-red-600 hover:bg-red-700 text-white font-bold rounded-lg transition-colors flex items-center gap-1.5 shadow-sm active:scale-95 disabled:opacity-50"
                  >
                    <span className="material-symbols-outlined text-[16px]">delete</span>
                    {batchDeleting ? 'Deleting...' : `Delete (${selectedJobIds.length})`}
                  </button>
                </div>
              </div>
            )}

            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-ash-100 font-prose text-xs font-bold text-ash-400 uppercase tracking-wider bg-ash-50/50">
                    <th className="py-4 pl-8 pr-2 w-10 text-center">
                      <input
                        type="checkbox"
                        checked={paginatedJobs.length > 0 && paginatedJobs.every((j) => selectedJobIds.includes(j.job_id))}
                        ref={(el) => {
                          if (el) {
                            const someSelected = paginatedJobs.some((j) => selectedJobIds.includes(j.job_id));
                            const allSelected = paginatedJobs.length > 0 && paginatedJobs.every((j) => selectedJobIds.includes(j.job_id));
                            el.indeterminate = someSelected && !allSelected;
                          }
                        }}
                        onChange={() => handleSelectAll(paginatedJobs)}
                        className="w-4 h-4 rounded text-brand-600 border-ash-300 focus:ring-brand-500 cursor-pointer accent-[#0085FF]"
                        title="Select/Deselect Page"
                      />
                    </th>
                    <th className="py-4 px-4">Filename / Judgment Title</th>
                    <th className="py-4 px-4">Status</th>
                    <th className="py-4 px-4">Uploaded by</th>
                    <th className="py-4 px-4">Uploaded</th>
                    <th className="py-4 px-8 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="font-prose text-sm divide-y divide-ash-50">
                  {recentLoading ? (
                    <tr>
                      <td colSpan="6" className="py-10 text-center text-ash-400">Loading ingestion activity...</td>
                    </tr>
                  ) : filteredJobs.length === 0 ? (
                    <tr>
                      <td colSpan="6" className="py-10 text-center text-ash-400">
                        {searchTerm ? 'No cases match your search.' : 'No ingestion jobs recorded.'}
                      </td>
                    </tr>
                  ) : (
                    paginatedJobs.map((job) => (
                      <tr
                        key={job.job_id}
                        className="hover:bg-ash-50/80 transition-colors align-top"
                      >
                        <td className="py-4 pl-8 pr-2 text-center">
                          <input
                            type="checkbox"
                            checked={selectedJobIds.includes(job.job_id)}
                            onChange={() => toggleSelectJob(job.job_id)}
                            className="w-4 h-4 rounded text-brand-600 border-ash-300 focus:ring-brand-500 cursor-pointer accent-[#0085FF]"
                          />
                        </td>
                        <td className="py-4 px-4 font-medium text-[#111827]">
                          <div className="flex items-start gap-3">
                            <div className="w-8 h-8 rounded-lg bg-[#111827]/5 text-[#111827] flex items-center justify-center flex-shrink-0">
                              <span className="material-symbols-outlined text-base">description</span>
                            </div>
                            <div className="min-w-0">
                              <span className="block truncate max-w-xs font-semibold">{job.filename || 'Unnamed document'}</span>
                              <span className="block font-mono text-[10px] text-ash-400">{job.job_id}</span>
                              {errorText(job) && caseState(job) !== 'complete' && (
                                <span
                                  className={`block mt-1 text-[11px] max-w-xs truncate ${caseState(job) === 'failed' ? 'text-red-700' : 'text-amber-700'}`}
                                  title={errorText(job)}
                                >
                                  {errorText(job)}
                                </span>
                              )}
                            </div>
                          </div>
                        </td>
                        <td className="py-4 px-4"><StatePill job={job} /></td>
                        <td className="py-4 px-4 text-xs text-ash-600" title={job.uploaded_by?.id || ''}>
                          {uploaderLabel(job)}
                        </td>
                        <td className="py-4 px-4 text-ash-400 text-xs">{formatRelativeTime(job.created_at)}</td>
                        <td className="py-4 px-8 text-right">
                          <RowActions job={job} onDelete={setDeleteTarget} />
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <AdminPagination currentPage={safeCurrentPage} totalPages={totalPages} onPageChange={setCurrentPage} />
          </div>
        </div>
      </main>

      {/* Delete Modal */}
      <AdminDeleteModal
        isOpen={!!deleteTarget}
        title="Delete Judgment Document"
        message={`Are you sure you want to delete "${deleteTarget?.filename}"? This will permanently delete the PDF file from Google Drive, MongoDB, ChromaDB vector store, and all associated indexing.`}
        onConfirm={confirmDeleteJob}
        onCancel={() => setDeleteTarget(null)}
      />

      {/* Batch Delete Confirmation Modal */}
      <AdminDeleteModal
        isOpen={showBatchDeleteModal}
        title={`Delete ${selectedJobIds.length} Judgment Documents`}
        message={`Are you sure you want to permanently delete these ${selectedJobIds.length} selected cases? This will remove their PDFs from Google Drive, MongoDB, ChromaDB vector store, and all associated indexing.`}
        confirmText={batchDeleting ? 'Deleting...' : `Delete ${selectedJobIds.length} Cases`}
        onConfirm={confirmBatchDelete}
        onCancel={() => setShowBatchDeleteModal(false)}
      />

      {/* View All Modal */}
      {showAllModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-[100] animate-fade-in">
          <div className="bg-white rounded-2xl w-full max-w-5xl max-h-[85vh] overflow-y-auto p-8 shadow-2xl relative border border-ash-100 flex flex-col gap-6">
            <div className="flex justify-between items-center">
              <div>
                <h3 className="font-display font-bold text-2xl text-[#111827]">Complete Case History</h3>
                <p className="font-prose text-xs text-ash-500 mt-1">All uploaded PDF judgments and their ingestion states.</p>
              </div>
              <button onClick={() => setShowAllModal(false)} className="text-ash-400 hover:text-ash-600 transition-colors">
                <span className="material-symbols-outlined text-2xl">close</span>
              </button>
            </div>

            {/* Modal Bulk Action Toolbar - Clean, No Background Highlight */}
            {selectedJobIds.length > 0 && (
              <div className="py-2.5 px-1 border-b border-ash-100 flex items-center justify-between text-xs font-prose animate-fade-in">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-[#0085FF]" />
                  <span className="font-semibold text-sm text-[#111827]">
                    {selectedJobIds.length} case{selectedJobIds.length > 1 ? 's' : ''} selected
                  </span>
                </div>
                <div className="flex items-center gap-4">
                  <button
                    type="button"
                    onClick={clearSelection}
                    className="text-xs font-medium text-ash-500 hover:text-[#111827] transition-colors"
                  >
                    Clear all
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowBatchDeleteModal(true)}
                    disabled={batchDeleting}
                    className="px-3.5 py-1.5 bg-red-600 hover:bg-red-700 text-white font-bold rounded-lg transition-colors flex items-center gap-1.5 shadow-sm active:scale-95 disabled:opacity-50"
                  >
                    <span className="material-symbols-outlined text-[16px]">delete</span>
                    {batchDeleting ? 'Deleting...' : `Delete (${selectedJobIds.length})`}
                  </button>
                </div>
              </div>
            )}

            {allJobsError && (
              <div role="alert" className="flex items-start gap-2.5 bg-red-50 text-red-700 p-4 rounded-xl text-xs font-prose">
                <span className="material-symbols-outlined shrink-0 text-base leading-5" aria-hidden="true">error</span>
                <span>{allJobsError}</span>
              </div>
            )}

            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse font-prose text-sm">
                <thead>
                  <tr className="border-b border-ash-100 text-xs font-bold text-ash-400 uppercase tracking-wider bg-ash-50/50">
                    <th className="py-3 px-3 w-10 text-center">
                      <input
                        type="checkbox"
                        checked={sortedAllJobs.length > 0 && sortedAllJobs.every((j) => selectedJobIds.includes(j.job_id))}
                        ref={(el) => {
                          if (el) {
                            const someSelected = sortedAllJobs.some((j) => selectedJobIds.includes(j.job_id));
                            const allSelected = sortedAllJobs.length > 0 && sortedAllJobs.every((j) => selectedJobIds.includes(j.job_id));
                            el.indeterminate = someSelected && !allSelected;
                          }
                        }}
                        onChange={() => handleSelectAll(sortedAllJobs)}
                        className="w-4 h-4 rounded text-brand-600 border-ash-300 focus:ring-brand-500 cursor-pointer accent-[#0085FF]"
                        title="Select/Deselect All"
                      />
                    </th>
                    <th className="py-3 px-4">Filename</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Uploaded by</th>
                    <th className="py-3 px-4">Uploaded</th>
                    <th className="py-3 px-4 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ash-50">
                  {allJobsLoading && sortedAllJobs.length === 0 ? (
                    <tr>
                      <td colSpan="6" className="py-8 text-center text-ash-400">Loading history...</td>
                    </tr>
                  ) : sortedAllJobs.length === 0 ? (
                    <tr>
                      <td colSpan="6" className="py-8 text-center text-ash-400">No uploads found.</td>
                    </tr>
                  ) : (
                    sortedAllJobs.map((job) => (
                      <tr
                        key={job.job_id}
                        className="hover:bg-ash-50 align-top transition-colors"
                      >
                        <td className="py-3.5 px-3 text-center">
                          <input
                            type="checkbox"
                            checked={selectedJobIds.includes(job.job_id)}
                            onChange={() => toggleSelectJob(job.job_id)}
                            className="w-4 h-4 rounded text-brand-600 border-ash-300 focus:ring-brand-500 cursor-pointer accent-[#0085FF]"
                          />
                        </td>
                        <td className="py-3.5 px-4 font-medium text-[#111827]">
                          <span className="block">{job.filename || 'Unnamed'}</span>
                          <span className="block font-mono text-[10px] text-ash-400">{job.job_id}</span>
                          {errorText(job) && caseState(job) !== 'complete' && (
                            <span className="block mt-1 text-[11px] text-red-700 max-w-xs truncate" title={errorText(job)}>
                              {errorText(job)}
                            </span>
                          )}
                        </td>
                        <td className="py-3.5 px-4"><StatePill job={job} /></td>
                        <td className="py-3.5 px-4 text-xs text-ash-600" title={job.uploaded_by?.id || ''}>
                          {uploaderLabel(job)}
                        </td>
                        <td className="py-3.5 px-4 text-xs text-ash-400">{formatRelativeTime(job.created_at)}</td>
                        <td className="py-3.5 px-4 text-right">
                          <RowActions
                            job={job}
                            onDelete={(target) => {
                              setDeleteTarget(target);
                            }}
                          />
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
