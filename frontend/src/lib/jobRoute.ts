import type { JobStatus } from '@/api/types';
import { paths } from '@/config/paths';

/** Where clicking into a job should land, based on how far it's progressed.
 * `batchId` is the job's UploadBatch id (Job.batch) — while a job is still
 * processing, or if it failed, that's its batch's Status page.
 * For a job with no batch (batchId == null), 'failed' covers two different
 * things: ingestion never produced a document at all (nothing to show —
 * entityCount 0), or a completion-time verification failure, where the
 * document and every entity are still there and the reviewer needs to get
 * back in to fix whatever survived (see documents/views.py's
 * JobDocumentView, which allows exactly this case) — `entityCount`
 * distinguishes the two instead of treating every non-batch failure as a
 * dead end. */
export function routeForJobStatus(
  id: number,
  status: JobStatus,
  batchId?: number | null,
  entityCount?: number,
): string | null {
  switch (status) {
    case 'complete':
      return paths.jobAudit.getHref(id);
    case 'failed':
<<<<<<< HEAD
      if (batchId != null) return `/uploads/${batchId}/status`;
      return (entityCount ?? 0) > 0 ? `/jobs/${id}/review` : null;
    case 'scanning':
    case 'queued':
      return batchId != null ? `/uploads/${batchId}/status` : `/jobs/${id}/rules`;
=======
      return batchId != null ? paths.uploadStatus.getHref(batchId) : null;
    case 'scanning':
      return batchId != null ? paths.uploadStatus.getHref(batchId) : paths.jobRules.getHref(id);
>>>>>>> feature/screen-map
    case 'in_review':
    case 'finalizing':
    default:
      return paths.jobReview.getHref(id);
  }
}
