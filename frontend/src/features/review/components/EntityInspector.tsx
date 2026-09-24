import { useMemo, useState } from 'react';
import type { Entity, Mode } from '@/api/types';
import { CategoryDot } from '@/components/CategoryBadge';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { categoryCfr, categoryLabel, MODE_LABELS, MODE_NOTES, MODES } from '@/lib/categories';

const FILTERS: (Mode | 'all')[] = ['all', 'redact', 'mask', 'pseudo', 'keep'];

const MODE_PILL_CLASSES: Record<Mode, string> = {
  redact: 'bg-mode-redact text-white border-transparent',
  mask: 'bg-mode-mask-bg text-mode-mask border-[#d7dce0]',
  pseudo: 'bg-white text-mode-pseudo border-mode-pseudo border-dashed',
  keep: 'bg-white text-mode-keep border-mode-keep border-dotted',
};

export function EntityInspector({
  entities,
  selectedCode,
  onSelect,
  onModeChange,
  busyId,
  threshold,
  readOnly,
}: {
  entities: Entity[];
  selectedCode: string | null;
  onSelect: (code: string) => void;
  onModeChange: (entity: Entity, mode: Mode) => void;
  busyId?: number | null;
  threshold?: number;
  readOnly?: boolean;
}) {
  const [filter, setFilter] = useState<Mode | 'all'>('all');

  const filtered = useMemo(
    () => entities.filter((e) => filter === 'all' || e.mode === filter),
    [entities, filter],
  );

  const selected = useMemo(
    () => entities.find((e) => e.code === selectedCode) ?? null,
    [entities, selectedCode],
  );

  function selectNext() {
    if (filtered.length === 0) return;
    const idx = filtered.findIndex((e) => e.code === selectedCode);
    const next = filtered[(idx + 1) % filtered.length];
    onSelect(next.code);
  }

  return (
    <div className="border-border bg-card flex h-full min-h-0 flex-col overflow-hidden rounded-md border">
      <div className="border-border flex-none border-b px-4 py-3.5">
        <div className="mb-2.75 flex items-baseline gap-2">
          <strong className="text-[13.5px]">Detected entities</strong>
          <span className="text-muted-foreground font-mono text-[11.5px]">{filtered.length} shown</span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {FILTERS.map((f) => {
            const count = f === 'all' ? entities.length : entities.filter((e) => e.mode === f).length;
            return (
              <Button
                key={f}
                type="button"
                variant={filter === f ? 'default' : 'outline'}
                size="sm"
                className="h-auto rounded-full px-2.5 py-0.75 text-[11px] font-medium"
                onClick={() => setFilter(f)}
              >
                {f === 'all' ? 'All' : MODE_LABELS[f]} {count}
              </Button>
            );
          })}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 && (
          <div className="text-muted-foreground p-4 text-[13.5px]">No entities match this filter.</div>
        )}
        {filtered.map((entity) => (
          <div
            key={entity.id}
            className={cn(
              'border-border hover:bg-muted/60 cursor-pointer border-b px-4 py-2.5',
              entity.code === selectedCode && 'bg-status-info-bg hover:bg-status-info-bg',
            )}
            onClick={() => onSelect(entity.code)}
          >
            <div className="flex items-center gap-2">
              <CategoryDot category={entity.category} />
              <span className="text-muted-foreground text-[11px] font-semibold tracking-[0.06em] uppercase">
                {categoryLabel(entity.category)}
              </span>
              <span className="text-muted-foreground ml-auto font-mono text-[10.5px]">
                {Math.round(entity.confidence * 100)}%
              </span>
              <Badge
                variant="outline"
                className={cn('font-mono text-[11px] font-semibold tracking-[0.02em]', MODE_PILL_CLASSES[entity.mode])}
              >
                {MODE_LABELS[entity.mode]}
              </Badge>
            </div>
            <div className="text-foreground mt-1 truncate font-mono text-xs">{entity.value}</div>
          </div>
        ))}
      </div>

      {selected && (
        <div className="border-border flex max-h-[42vh] flex-none flex-col gap-3.25 overflow-y-auto border-t bg-[#fbfaf7] px-4 pt-3.75 pb-4.25">
          <div>
            <div className="text-muted-foreground mb-0.5 block text-xs font-semibold">
              Selected · {categoryLabel(selected.category)}
            </div>
            <div className="text-foreground font-mono text-[13px] break-all">{selected.value}</div>
            <div className="text-muted-foreground mt-0.5 text-[13.5px]">
              {selected.code} · page {selected.page} · confidence{' '}
              {Math.round(selected.confidence * 100)}%
              {threshold != null && selected.confidence < threshold ? ' · below threshold' : ''}
            </div>
          </div>
          <div>
            <div className="text-muted-foreground mb-1.5 block text-xs font-semibold">Transformation</div>
            <div className="grid grid-cols-4 gap-1.25">
              {MODES.map((mode) => {
                const active = mode === selected.mode;
                return (
                  <Button
                    key={mode}
                    type="button"
                    variant={active ? 'default' : 'outline'}
                    size="sm"
                    className="h-auto min-h-8 min-w-0 px-1.5 py-1 text-center text-[12px] leading-tight whitespace-normal wrap-anywhere"
                    disabled={readOnly || busyId === selected.id}
                    title={readOnly ? 'Reopen this document to change entities.' : MODE_NOTES[mode]}
                    onClick={() => onModeChange(selected, mode)}
                  >
                    {MODE_LABELS[mode]}
                  </Button>
                );
              })}
            </div>
            <p className="text-muted-foreground mt-1.75 mb-0 text-[13.5px] leading-normal">
              {MODE_NOTES[selected.mode]}
            </p>
          </div>
          <div className="border-border flex items-center gap-2 border-t pt-2">
            <span className="text-muted-foreground font-mono text-[10.5px]">{categoryCfr(selected.category)}</span>
            <Button size="sm" className="ml-auto" onClick={selectNext}>
              Next entity →
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
