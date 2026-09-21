import type { JobStatus } from '@/api/types';
import { formatStatus } from '@/lib/format';

export function StatusBadge({ status }: { status: JobStatus }) {
  return <span className={`badge status-badge-${status}`}>{formatStatus(status)}</span>;
}
