import type { JobStatus } from '../api/types';

/** Where clicking into a job should land, based on how far it's progressed. */
export function routeForJobStatus(id: number, status: JobStatus): string | null {
  switch (status) {
    case 'complete':
      return `/jobs/${id}/audit`;
    case 'failed':
      return null;
    case 'scanning':
      return `/jobs/${id}/rules`;
    case 'in_review':
    default:
      return `/jobs/${id}/review`;
  }
}
