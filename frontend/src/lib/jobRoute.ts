import type { JobStatus } from '@/api/types';

/** Where clicking into a job should land, based on how far it's progressed.
 * `batchId` is the job's UploadBatch id (Job.batch) — while a job is still
 * processing, or if it failed, that's its batch's Status page; jobs created
 * before batch uploads existed (batchId == null) fall back to a dead end for
 * 'failed' since there's nowhere else to send them. */
export function routeForJobStatus(id: number, status: JobStatus, batchId?: number | null): string | null {
  switch (status) {
    case 'complete':
      return `/jobs/${id}/audit`;
    case 'failed':
      return batchId != null ? `/uploads/${batchId}/status` : null;
    case 'scanning':
      return batchId != null ? `/uploads/${batchId}/status` : `/jobs/${id}/rules`;
    case 'in_review':
    default:
      return `/jobs/${id}/review`;
  }
}
