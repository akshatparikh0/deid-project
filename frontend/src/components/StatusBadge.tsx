import type { JobStatus } from '@/api/types';
import { Badge } from '@/components/ui/badge';
import { formatStatus } from '@/lib/format';
import { cn } from '@/lib/utils';

const STATUS_CLASSES: Record<JobStatus, string> = {
  scanning: 'bg-status-warning-bg text-status-warning',
  in_review: 'bg-status-info-bg text-status-info',
  complete: 'bg-status-success-bg text-status-success',
  failed: 'bg-status-danger-bg text-destructive',
};

export function StatusBadge({ status }: { status: JobStatus }) {
  return (
    <Badge variant="outline" className={cn('border-transparent', STATUS_CLASSES[status])}>
      {formatStatus(status)}
    </Badge>
  );
}
