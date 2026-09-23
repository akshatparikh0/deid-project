import type { JobStatus } from '@/api/types';
import { paths } from '@/config/paths';

/** Where clicking into a job should land, based on how far it's progressed.
 * `batchId` is the job's UploadBatch id (Job.batch) — while a job is still
 * processing, or if it failed, that's its batch's Status page; jobs created
 * before batch uploads existed (batchId == null) fall back to a dead end for
 * 'failed' since there's nowhere else to send them. */
export function routeForJobStatus(id: number, status: JobStatus, batchId?: number | null): string | null {
  switch (status) {
    case 'complete':
      return paths.jobAudit.getHref(id);
    case 'failed':
      return batchId != null ? paths.uploadStatus.getHref(batchId) : null;
    case 'scanning':
      return batchId != null ? paths.uploadStatus.getHref(batchId) : paths.jobRules.getHref(id);
    case 'in_review':
    default:
      return paths.jobReview.getHref(id);
  }
}
