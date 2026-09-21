import { useMemo, useState } from 'react';
import type { Entity, Mode } from '@/api/types';
import { CategoryDot } from '@/components/CategoryBadge';
import { categoryCfr, categoryLabel, MODE_LABELS, MODE_NOTES, MODES } from '@/lib/categories';

const FILTERS: (Mode | 'all')[] = ['all', 'redact', 'mask', 'pseudo', 'keep'];

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
    <div className="card entity-inspector">
      <div className="entity-inspector-header">
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 11 }}>
          <strong style={{ fontSize: 13.5 }}>Detected entities</strong>
          <span className="mono" style={{ fontSize: 11.5, color: 'var(--color-text-faint)' }}>
            {filtered.length} shown
          </span>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {FILTERS.map((f) => {
            const count = f === 'all' ? entities.length : entities.filter((e) => e.mode === f).length;
            return (
              <button
                key={f}
                type="button"
                className={`chip${filter === f ? ' chip-active' : ''}`}
                onClick={() => setFilter(f)}
              >
                {f === 'all' ? 'All' : MODE_LABELS[f]} {count}
              </button>
            );
          })}
        </div>
      </div>

      <div className="entity-inspector-list">
        {filtered.length === 0 && (
          <div className="page-subtitle" style={{ padding: 16 }}>
            No entities match this filter.
          </div>
        )}
        {filtered.map((entity) => (
          <div
            key={entity.id}
            className={`entity-row${entity.code === selectedCode ? ' entity-row-selected' : ''}`}
            onClick={() => onSelect(entity.code)}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <CategoryDot category={entity.category} />
              <span
                style={{
                  fontSize: 11,
                  letterSpacing: '0.06em',
                  textTransform: 'uppercase',
                  color: 'var(--color-text-muted)',
                  fontWeight: 600,
                }}
              >
                {categoryLabel(entity.category)}
              </span>
              <span className="mono" style={{ marginLeft: 'auto', fontSize: 10.5, color: 'var(--color-text-faint)' }}>
                {Math.round(entity.confidence * 100)}%
              </span>
              <span className={`mode-pill mode-pill-${entity.mode}`}>{MODE_LABELS[entity.mode]}</span>
            </div>
            <div
              className="mono"
              style={{
                marginTop: 4,
                fontSize: 12,
                color: 'var(--color-text)',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {entity.value}
            </div>
          </div>
        ))}
      </div>

      {selected && (
        <div className="entity-detail">
          <div>
            <div className="field-label" style={{ marginBottom: 2 }}>
              Selected · {categoryLabel(selected.category)}
            </div>
            <div className="entity-detail-value">{selected.value}</div>
            <div className="page-subtitle" style={{ marginTop: 2 }}>
              {selected.code} · page {selected.page} · confidence{' '}
              {Math.round(selected.confidence * 100)}%
              {threshold != null && selected.confidence < threshold ? ' · below threshold' : ''}
            </div>
          </div>
          <div>
            <div className="field-label" style={{ marginBottom: 6 }}>
              Transformation
            </div>
            <div className="entity-detail-mode-grid">
              {MODES.map((mode) => {
                const active = mode === selected.mode;
                return (
                  <button
                    key={mode}
                    type="button"
                    disabled={readOnly || busyId === selected.id}
                    title={readOnly ? 'Reopen this document to change entities.' : MODE_NOTES[mode]}
                    className={`seg-btn-solid${active ? ' seg-btn-solid-active' : ''}`}
                    onClick={() => onModeChange(selected, mode)}
                  >
                    {MODE_LABELS[mode]}
                  </button>
                );
              })}
            </div>
            <p className="page-subtitle" style={{ marginTop: 7, marginBottom: 0, lineHeight: 1.5 }}>
              {MODE_NOTES[selected.mode]}
            </p>
          </div>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              paddingTop: 8,
              borderTop: '1px solid var(--color-border)',
            }}
          >
            <span className="mono" style={{ fontSize: 10.5, color: 'var(--color-text-faint)' }}>
              {categoryCfr(selected.category)}
            </span>
            <button className="btn btn-sm btn-primary" style={{ marginLeft: 'auto' }} onClick={selectNext}>
              Next entity →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
