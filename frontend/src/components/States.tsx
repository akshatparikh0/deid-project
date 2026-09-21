import type { ReactNode } from 'react';
import { Loader2, TriangleAlert } from 'lucide-react';
import { Button } from '@/components/ui/button';

export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      role="alert"
      className="bg-status-danger-bg text-destructive mb-4.5 flex items-start gap-2.5 rounded-md border border-destructive/20 px-3.5 py-3 text-[13px]"
    >
      <TriangleAlert className="mt-0.5 size-4 shrink-0" />
      <div className="flex-1">{message}</div>
      {onRetry && (
        <Button size="sm" variant="outline" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="text-muted-foreground flex items-center gap-2.5 py-10 text-[13.5px]">
      <Loader2 className="size-4 animate-spin" />
      {label}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="text-muted-foreground px-6 py-16 text-center">
      <h3 className="font-serif text-foreground mb-1.5 font-medium">{title}</h3>
      {description && <p>{description}</p>}
      {action}
    </div>
  );
}
