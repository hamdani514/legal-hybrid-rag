/* Upload rows' state rules, shared by the Cases page and its upload queue. */

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

/*
 * A row that ended badly: rejected by the server, cancelled, deleted, failed,
 * or stalled because the server lost the task. The batch panel stays on screen
 * when any row ends this way, so the admin sees the problem and can retry.
 */
export const isRowProblem = (item) => {
  if (['rejected', 'cancelled', 'removed'].includes(item.state)) return true;
  if (item.state !== 'tracking') return false;
  const status = item.status || '';
  if (status === 'failed' || status.endsWith('_failed')) return true;
  // `active: false` means the server holds no task for this job. That is a
  // stall only while the job is unfinished — a job that COMPLETED is also
  // inactive, and reading that as a problem kept every finished batch on
  // screen. rowView() orders these checks the same way.
  return !isTerminalJob(status) && item.active === false;
};
