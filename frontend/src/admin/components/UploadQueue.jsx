import React from 'react';

/*
 * Progress of a multi-file upload on the Cases page.
 *
 * Each file is its own upload request and its own judgment on the server. A
 * row goes: waiting (in the browser) -> uploading -> tracking (the server's
 * job status: queued, extracting, parsing, ... searchable/complete/failed),
 * or rejected (duplicate, not a judgment, server unreachable) / cancelled.
 */

export const TERMINAL_JOB_STATUSES = ['searchable', 'complete', 'failed'];

export const isTerminalJob = (status) =>
  TERMINAL_JOB_STATUSES.includes(status) || (status || '').endsWith('_failed');

const SERVER_LABELS = {
  uploaded: 'In queue',
  queued: 'In queue',
  extracting: 'Extracting text',
  extracted: 'Text extracted',
  parsing: 'Parsing sections',
  parsed: 'Parsed',
  tree: 'Building tree',
  embedding: 'Indexing',
  indexing: 'Indexing',
  searchable: 'Searchable',
  complete: 'Complete',
};

/** One label and tone per row. */
export const rowView = (item) => {
  if (item.state === 'waiting') return { label: 'Waiting to upload', tone: 'idle' };
  if (item.state === 'uploading') return { label: 'Uploading', tone: 'busy' };
  if (item.state === 'cancelled') return { label: 'Not uploaded', tone: 'idle' };
  if (item.state === 'rejected') return { label: 'Rejected', tone: 'bad' };
  if (item.state === 'removed') return { label: 'Deleted', tone: 'idle' };
  const status = item.status || 'uploaded';
  if (status === 'complete' || status === 'searchable') return { label: SERVER_LABELS[status], tone: 'good' };
  if (status === 'failed' || status.endsWith('_failed')) {
    return { label: `Failed: ${status.replace('_failed', '').replace('_', ' ')}`, tone: 'bad' };
  }
  // The server lost the task (restarted) while this job was in flight.
  if (item.active === false) return { label: 'Stalled - use Retry below', tone: 'warn' };
  return { label: SERVER_LABELS[status] || status, tone: 'busy' };
};

export const isRowFinished = (item) =>
  ['rejected', 'cancelled', 'removed'].includes(item.state) ||
  (item.state === 'tracking' && (isTerminalJob(item.status) || item.active === false));

const TONE = {
  idle: 'bg-ash-100 text-ash-600',
  busy: 'bg-amber-100 text-amber-800',
  good: 'bg-mint-400/30 text-green-800',
  bad: 'bg-red-100 text-red-800',
  warn: 'bg-amber-100 text-amber-800',
};

const ICON = {
  idle: 'schedule',
  busy: 'progress_activity',
  good: 'task_alt',
  bad: 'error',
  warn: 'warning',
};

const formatSize = (bytes) => {
  if (!bytes && bytes !== 0) return '';
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const UploadQueue = ({ queue, onCancelWaiting, onClearFinished }) => {
  if (!queue.length) return null;

  const counts = queue.reduce(
    (acc, item) => {
      const { tone } = rowView(item);
      if (item.state === 'waiting') acc.waiting += 1;
      else if (item.state === 'uploading') acc.uploading += 1;
      else if (item.state === 'rejected') acc.rejected += 1;
      else if (item.state === 'cancelled') acc.cancelled += 1;
      else if (tone === 'good') acc.done += 1;
      else if (tone === 'bad') acc.failed += 1;
      else if (tone === 'warn') acc.stalled += 1;
      else if (item.state === 'tracking') acc.processing += 1;
      return acc;
    },
    { waiting: 0, uploading: 0, processing: 0, done: 0, failed: 0, rejected: 0, cancelled: 0, stalled: 0 }
  );
  const finished = queue.filter(isRowFinished).length;
  const percent = Math.round((finished / queue.length) * 100);
  const allFinished = finished === queue.length;

  const summary = [
    counts.waiting && `${counts.waiting} waiting`,
    counts.uploading && `${counts.uploading} uploading`,
    counts.processing && `${counts.processing} processing`,
    counts.done && `${counts.done} searchable`,
    counts.failed && `${counts.failed} failed`,
    counts.stalled && `${counts.stalled} stalled`,
    counts.rejected && `${counts.rejected} rejected`,
    counts.cancelled && `${counts.cancelled} not uploaded`,
  ].filter(Boolean);

  return (
    <div className="rounded-3xl border border-ash-200 bg-white shadow-soft overflow-hidden">
      <div className="p-6 border-b border-ash-100 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h3 className="font-display font-bold text-lg text-[#111827]">
            {allFinished ? 'Batch finished' : `Processing ${queue.length} judgment${queue.length > 1 ? 's' : ''}`}
          </h3>
          <p className="font-prose text-xs text-ash-500 mt-1">{summary.join(' · ')}</p>
          <p className="font-prose text-[11px] text-ash-400 mt-1">
            Each PDF is processed as its own judgment. Two are extracted and parsed at a time, and they are indexed
            one by one, so no two judgments ever share data.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {counts.waiting > 0 && (
            <button
              onClick={onCancelWaiting}
              className="px-4 py-2 rounded-lg border border-ash-200 text-xs font-bold text-ash-700 hover:bg-ash-50 transition-colors"
              title="Files already uploaded keep processing on the server"
            >
              Cancel remaining
            </button>
          )}
          {finished > 0 && (
            <button
              onClick={onClearFinished}
              className="px-4 py-2 rounded-lg border border-ash-200 text-xs font-bold text-ash-700 hover:bg-ash-50 transition-colors"
            >
              {allFinished ? 'Close' : 'Clear finished'}
            </button>
          )}
        </div>
      </div>

      <div className="px-6 pt-4">
        <div className="h-2 w-full rounded-full bg-ash-100 overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-brand-500 to-brand-700 transition-all duration-500"
            style={{ width: `${percent}%` }}
          />
        </div>
        <p className="text-right font-prose text-[11px] text-ash-500 mt-1">
          {finished} of {queue.length} finished
        </p>
      </div>

      <ul className="max-h-80 overflow-y-auto divide-y divide-ash-100 px-2 pb-2">
        {queue.map((item) => {
          const view = rowView(item);
          return (
            <li key={item.key} className="flex items-start gap-3 px-4 py-3">
              <span
                className={`material-symbols-outlined text-lg mt-0.5 ${
                  view.tone === 'good' ? 'text-green-700' : view.tone === 'bad' ? 'text-red-600' : 'text-ash-400'
                } ${view.tone === 'busy' ? 'animate-spin' : ''}`}
              >
                {ICON[view.tone]}
              </span>
              <div className="flex-1 min-w-0">
                <p className="font-prose text-sm text-[#111827] truncate" title={item.name}>
                  {item.name}
                </p>
                <p className="font-prose text-[11px] text-ash-400">{formatSize(item.size)}</p>
                {item.error && <p className="font-prose text-[11px] text-red-700 mt-0.5">{item.error}</p>}
                {item.notice && !item.error && (
                  <p className="font-prose text-[11px] text-brand-600 mt-0.5">{item.notice}</p>
                )}
              </div>
              <span className={`shrink-0 px-2.5 py-1 rounded-full text-[11px] font-semibold ${TONE[view.tone]}`}>
                {view.label}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
};

export default UploadQueue;
