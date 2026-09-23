import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ApiError, getUploadBatch, retryJob } from '@/api/client';
import type { Job, JobStage, StageName, UploadBatch } from '@/api/types';
import { PageHeader } from '@/components/Layout';
import { ErrorBanner, LoadingState } from '@/components/States';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { paths } from '@/config/paths';
import { formatDuration } from '@/lib/format';
import { cn } from '@/lib/utils';
import { setActiveBatch } from '@/stores/activeJob';

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
    <div className="flex flex-1 basis-80 items-center gap-1">
      {stages.map((stage, i) => (
        <div className="flex min-w-0 flex-1 items-center gap-1.5" key={stage.name}>
          <div className="flex min-w-0 flex-col gap-px">
            <span
              className={cn(
                'text-muted-foreground flex items-center text-[11px] whitespace-nowrap',
                stage.status === 'running' && 'text-status-info font-semibold',
                stage.status === 'failed' && 'text-destructive font-semibold',
              )}
            >
              <span
                className={cn(
                  'border-border bg-card mr-1.25 size-2.25 shrink-0 rounded-full border-1.5',
                  stage.status === 'done' && 'border-status-success bg-status-success',
                  stage.status === 'running' && 'border-status-info bg-status-info animate-pulse',
                  stage.status === 'failed' && 'border-destructive bg-destructive',
                )}
              />
              {STAGE_LABELS[stage.name]}
            </span>
            {stage.duration_seconds != null && (stage.status === 'done' || stage.status === 'failed') && (
              <span className="text-muted-foreground font-mono text-[10.5px] whitespace-nowrap">
                {formatDuration(stage.duration_seconds)}
              </span>
            )}
          </div>
          {i < stages.length - 1 && <div className="bg-border h-px min-w-2 flex-1" />}
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
        actions={
          <Button variant="outline" size="sm" onClick={() => navigate(paths.queue.getHref(batch.folder))}>
            View in library
          </Button>
        }
      />

      {error && <ErrorBanner message={error} />}

      <Progress value={progressPct} className="h-1.5" />

      <Card className="mt-5 gap-0 py-0">
        {[...batch.jobs].reverse().map((job) => {
          const canReview = job.status === 'in_review' || job.status === 'complete';
          return (
            <div
              key={job.id}
              className="border-border flex flex-wrap items-center gap-4 border-b px-4 py-3.5 last:border-b-0"
            >
              <div className="flex-1 basis-50 overflow-hidden text-[13.5px] font-medium text-ellipsis whitespace-nowrap" title={job.filename}>
                {job.filename}
              </div>

              {job.status === 'failed' ? (
                <div className="flex-2 basis-80">
                  <ErrorBanner
                    message={job.error_message || 'This file could not be processed.'}
                    onRetry={retrying === job.id ? undefined : () => onRetry(job.id)}
                  />
                </div>
              ) : (
                <>
                  <StageTimeline stages={job.stages ?? []} />
                  <span className="text-muted-foreground flex-none basis-25 text-[11px]">
                    {currentPhaseLabel(job)}
                  </span>
                </>
              )}

              <div className="flex flex-none gap-2">
                <Button
                  type="button"
                  size="sm"
                  disabled={!canReview}
                  onClick={() => navigate(paths.jobReview.getHref(job.id), { state: { from: 'status' } })}
                >
                  Review
                </Button>
              </div>
            </div>
          );
        })}
      </Card>
    </div>
  );
}
