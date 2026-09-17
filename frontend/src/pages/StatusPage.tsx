import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ApiError, getUploadBatch, retryJob } from '../api/client';
import type { Job, JobStage, StageName, UploadBatch } from '../api/types';
import { PageHeader } from '../components/Layout';
import { ErrorBanner, LoadingState } from '../components/States';
import { setActiveBatch } from '../lib/activeJob';
import { formatDuration } from '../lib/format';

const STAGE_LABELS: Record<StageName, string> = {
  ingest: 'Ingest',
  parse: 'Parse',
  detect: 'Detect',
  transform: 'Transform',
  finalize: 'Finalize',
};

const TERMINAL_STATUSES = new Set(['in_review', 'complete', 'failed']);

const POLL_INTERVAL_MS = 1500;

function isTerminal(batch: UploadBatch): boolean {
  return batch.jobs.every((job) => TERMINAL_STATUSES.has(job.status));
}

/** A short phrase for what's happening to this file right now, shown next
 * to its stage timeline — "Queued" covers the gap between the file being
 * saved and a worker thread actually picking it up (see tasks.py). */
function currentPhaseLabel(job: Job): string {
  if (job.status === 'failed') return 'Failed';
  if (job.status === 'in_review' || job.status === 'complete') return 'Ready for review';
  const running = job.stages?.find((s) => s.status === 'running');
  if (running) return `${STAGE_LABELS[running.name]}…`;
  return 'Queued';
}

function StageTimeline({ stages }: { stages: JobStage[] }) {
  return (
    <div className="stage-timeline">
      {stages.map((stage, i) => (
        <div className="stage-step" key={stage.name}>
          <div className="stage-label-group">
            <span
              className={`stage-label${stage.status === 'running' ? ' stage-label-running' : ''}${
                stage.status === 'failed' ? ' stage-label-failed' : ''
              }`}
            >
              <span className={`stage-dot stage-dot-${stage.status}`} style={{ marginRight: 5 }} />
              {STAGE_LABELS[stage.name]}
            </span>
            {stage.duration_seconds != null && (stage.status === 'done' || stage.status === 'failed') && (
              <span className="stage-duration">{formatDuration(stage.duration_seconds)}</span>
            )}
          </div>
          {i < stages.length - 1 && <div className="stage-connector" />}
        </div>
      ))}
    </div>
  );
}

export function StatusPage() {
  const { batchId } = useParams<{ batchId: string }>();
  const id = Number(batchId);
  const navigate = useNavigate();

  const [batch, setBatch] = useState<UploadBatch | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState<number | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  function load() {
    getUploadBatch(id)
      .then((res) => {
        setBatch(res.batch);
        setActiveBatch(res.batch.id);
        setError(null);
        if (isTerminal(res.batch) && intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.detail : 'Failed to load upload status.');
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
    intervalRef.current = setInterval(load, POLL_INTERVAL_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function onRetry(jobId: number) {
    setRetrying(jobId);
    try {
      await retryJob(jobId);
      if (!intervalRef.current) intervalRef.current = setInterval(load, POLL_INTERVAL_MS);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to retry this file.');
    } finally {
      setRetrying(null);
    }
  }

  if (loading && !batch) return <LoadingState label="Loading upload status…" />;
  if (error && !batch) return <ErrorBanner message={error} onRetry={load} />;
  if (!batch) return null;

  const progressPct = batch.total > 0 ? Math.round((batch.finished / batch.total) * 100) : 0;
  const allDone = isTerminal(batch);

  return (
    <div>
      <PageHeader
        title="Processing documents"
        subtitle={
          allDone
            ? `All ${batch.total} file${batch.total === 1 ? '' : 's'} processed.`
            : `Processing ${batch.finished} of ${batch.total} file${batch.total === 1 ? '' : 's'}…`
        }
      />

      {error && <ErrorBanner message={error} />}

      <div className="batch-progress-track">
        <div className="batch-progress-fill" style={{ width: `${progressPct}%` }} />
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        {batch.jobs.map((job) => {
          const canReview = job.status === 'in_review' || job.status === 'complete';
          return (
            <div key={job.id} className="batch-file-row">
              <div className="batch-file-name" title={job.filename}>
                {job.filename}
              </div>

              {job.status === 'failed' ? (
                <div style={{ flex: '2 1 320px' }}>
                  <ErrorBanner
                    message={job.error_message || 'This file could not be processed.'}
                    onRetry={retrying === job.id ? undefined : () => onRetry(job.id)}
                  />
                </div>
              ) : (
                <>
                  <StageTimeline stages={job.stages ?? []} />
                  <span className="stage-label" style={{ flex: '0 0 100px' }}>
                    {currentPhaseLabel(job)}
                  </span>
                </>
              )}

              <div className="batch-file-actions">
                <button
                  type="button"
                  className="btn btn-sm btn-primary"
                  disabled={!canReview}
                  onClick={() => navigate(`/jobs/${job.id}/review`, { state: { from: 'status' } })}
                >
                  Review
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
