import type { JobStatus } from '@/api/types';
import { paths } from '@/config/paths';

/** Where clicking into a job should land, based on how far it's progressed.
 * `batchId` is the job's UploadBatch id (Job.batch) — while a job is still
 * processing, or if it failed, that's its batch's Status page.
 * For a job with no batch (batchId == null), a 'failed' job with no
 * entities means ingestion never produced a document at all (nothing to
 * show); `entityCount` distinguishes that dead end from a 'failed' job
 * that does have a reviewable document (see documents/views.py's
 * JobDocumentView, which allows exactly this case). */
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
      if (batchId != null) return paths.uploadStatus.getHref(batchId);
      return (entityCount ?? 0) > 0 ? paths.jobReview.getHref(id) : null;
    case 'scanning':
    case 'queued':
      return batchId != null ? paths.uploadStatus.getHref(batchId) : paths.jobRules.getHref(id);
    case 'in_review':
    case 'finalizing':
    default:
      return paths.jobReview.getHref(id);
  }
}
