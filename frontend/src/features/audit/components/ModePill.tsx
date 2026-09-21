import type { Mode } from '@/api/types';
import { Badge } from '@/components/ui/badge';
import { MODE_LABELS } from '@/lib/categories';
import { cn } from '@/lib/utils';

const MODE_CLASSES: Record<Mode, string> = {
  redact: 'bg-mode-redact text-white border-transparent',
  mask: 'bg-mode-mask-bg text-mode-mask border-transparent',
  pseudo: 'bg-background text-mode-pseudo border-dashed border-mode-pseudo',
  keep: 'bg-background text-mode-keep border-dotted border-mode-keep',
};

export function ModePill({ mode }: { mode: Mode }) {
  return (
    <Badge variant="outline" className={cn('font-mono', MODE_CLASSES[mode])}>
      {MODE_LABELS[mode]}
    </Badge>
  );
}
