import { useEffect, useRef, useState } from 'react';
import { fetchAuthenticatedBlob } from '../api/client';
import type { Category, DocumentPage, Entity } from '../api/types';
import { categoryColor } from '../lib/categories';

function hexToRgba(hex: string, alpha: number): string {
  const m = hex.replace('#', '');
  const r = parseInt(m.substring(0, 2), 16);
  const g = parseInt(m.substring(2, 4), 16);
  const b = parseInt(m.substring(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function PageImage({ page }: { page: DocumentPage }) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    fetchAuthenticatedBlob(page.image_url)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setSrc(objectUrl);
      })
      .catch(() => {
        // Left blank on failure — the overlay boxes below still convey which
        // regions are entities even without the page image itself.
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [page.image_url]);

  if (!src) return <div className="pdf-page-loading">Loading page {page.number}…</div>;
  return <img src={src} alt={`Page ${page.number}`} draggable={false} />;
}

function EntityOverlay({
  entity,
  scale,
  variant,
  ruleTokenByCategory,
  selectedCode,
  onSelect,
  dimThreshold,
}: {
  entity: Entity;
  scale: number;
  variant: 'original' | 'deidentified';
  ruleTokenByCategory: Partial<Record<Category, string>>;
  selectedCode: string | null;
  onSelect: (code: string) => void;
  dimThreshold?: number;
}) {
  const selected = entity.code === selectedCode;
  const dim = dimThreshold != null && entity.confidence < dimThreshold;

  return (
    <>
      {entity.boxes.map((box, i) => {
        const style: React.CSSProperties = {
          position: 'absolute',
          left: box.x0 * scale,
          top: box.top * scale,
          width: Math.max(2, (box.x1 - box.x0) * scale),
          height: Math.max(2, (box.bottom - box.top) * scale),
        };
        const fontSize = Math.max(8, Math.min(13, (box.bottom - box.top) * scale * 0.6));
        const overlayKey = `${entity.code}-${i}`;
        const common = {
          className: 'pdf-page-overlay',
          'data-entity-code': entity.code,
          onClick: () => onSelect(entity.code),
        };

        if (variant === 'original') {
          const color = categoryColor(entity.category);
          return (
            <div
              key={overlayKey}
              {...common}
              title={`${entity.code} · ${Math.round(entity.confidence * 100)}% confidence`}
              style={{
                ...style,
                background: hexToRgba(color, dim ? 0.08 : selected ? 0.32 : 0.16),
                border: `1.5px solid ${hexToRgba(color, dim ? 0.45 : 1)}`,
                boxShadow: selected ? `0 0 0 2px ${hexToRgba(color, 0.5)}` : 'none',
                opacity: dim ? 0.75 : 1,
              }}
            />
          );
        }

        if (entity.mode === 'keep') {
          return (
            <div
              key={overlayKey}
              {...common}
              title={`${entity.code} · kept`}
              style={{
                ...style,
                border: '1.5px dotted var(--mode-keep)',
                background: 'rgba(184, 121, 45, 0.06)',
                boxShadow: selected ? '0 0 0 2px var(--mode-keep)' : 'none',
                opacity: dim ? 0.75 : 1,
              }}
            />
          );
        }

        // Coverage boxes (redact/mask/pseudo) must stay fully opaque no
        // matter what — they're hiding the real PHI pixels underneath, not
        // just styling text. A low-confidence entity still gets flagged
        // (a dashed amber ring), but never by punching a see-through hole
        // in its own redaction.
        const lowConfidenceRing = dim && !selected ? '0 0 0 2px var(--mode-keep)' : null;

        if (entity.mode === 'redact') {
          return (
            <div
              key={overlayKey}
              {...common}
              title={`${entity.code} · redacted${dim ? ' · low confidence' : ''}`}
              style={{
                ...style,
                background: 'var(--mode-redact)',
                boxShadow: selected ? '0 0 0 2px var(--color-success)' : lowConfidenceRing || 'none',
              }}
            />
          );
        }

        if (entity.mode === 'pseudo') {
          const label = entity.surrogate_value || entity.value;
          return (
            <div
              key={overlayKey}
              {...common}
              title={`${entity.code} · pseudonymized${dim ? ' · low confidence' : ''}`}
              style={{
                ...style,
                background: '#eaf1fa',
                borderBottom: '2px dashed var(--mode-pseudo)',
                boxShadow: selected ? '0 0 0 2px var(--mode-pseudo)' : lowConfidenceRing || 'none',
                display: 'flex',
                alignItems: 'center',
                overflow: 'hidden',
              }}
            >
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize,
                  color: 'var(--mode-pseudo)',
                  whiteSpace: 'nowrap',
                  padding: '0 2px',
                }}
              >
                {label}
              </span>
            </div>
          );
        }

        // mask (default)
        const token = ruleTokenByCategory[entity.category] ?? `[${entity.category.toUpperCase()}]`;
        return (
          <div
            key={overlayKey}
            {...common}
            title={`${entity.code} · masked${dim ? ' · low confidence' : ''}`}
            style={{
              ...style,
              background: 'var(--mode-mask-bg)',
              border: '1px solid #d7dce0',
              borderRadius: 3,
              boxShadow: selected ? '0 0 0 2px var(--mode-mask)' : lowConfidenceRing || 'none',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              overflow: 'hidden',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize,
                fontWeight: 600,
                color: 'var(--mode-mask)',
                whiteSpace: 'nowrap',
              }}
            >
              {token}
            </span>
          </div>
        );
      })}
    </>
  );
}

function PageCanvas({
  page,
  entities,
  variant,
  ruleTokenByCategory,
  selectedCode,
  onSelect,
  dimThreshold,
}: {
  page: DocumentPage;
  entities: Entity[];
  variant: 'original' | 'deidentified';
  ruleTokenByCategory: Partial<Record<Category, string>>;
  selectedCode: string | null;
  onSelect: (code: string) => void;
  dimThreshold?: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const update = () => setScale(el.clientWidth / page.width);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, [page.width]);

  return (
    <div ref={containerRef} className="pdf-page" style={{ aspectRatio: `${page.width} / ${page.height}` }}>
      <PageImage page={page} />
      {scale > 0 &&
        entities.map((entity) => (
          <EntityOverlay
            key={entity.code}
            entity={entity}
            scale={scale}
            variant={variant}
            ruleTokenByCategory={ruleTokenByCategory}
            selectedCode={selectedCode}
            onSelect={onSelect}
            dimThreshold={dimThreshold}
          />
        ))}
    </div>
  );
}

export function PageImagePane({
  title,
  variant,
  pages,
  entitiesByPage,
  ruleTokenByCategory,
  selectedCode,
  onSelect,
  dimThreshold,
}: {
  title: string;
  variant: 'original' | 'deidentified';
  pages: DocumentPage[];
  entitiesByPage: Map<number, Entity[]>;
  ruleTokenByCategory: Partial<Record<Category, string>>;
  selectedCode: string | null;
  onSelect: (code: string) => void;
  dimThreshold?: number;
}) {
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!selectedCode || !bodyRef.current) return;
    const el = bodyRef.current.querySelector(`[data-entity-code="${selectedCode}"]`);
    el?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [selectedCode]);

  return (
    <div className="card doc-pane">
      <div className="doc-pane-header">{title}</div>
      <div className="doc-pane-body doc-pane-body-pages" ref={bodyRef}>
        {pages.map((page) => (
          <div key={page.number}>
            <div className="doc-page-break">Page {page.number}</div>
            <PageCanvas
              page={page}
              entities={entitiesByPage.get(page.number) ?? []}
              variant={variant}
              ruleTokenByCategory={ruleTokenByCategory}
              selectedCode={selectedCode}
              onSelect={onSelect}
              dimThreshold={dimThreshold}
            />
          </div>
        ))}
        {pages.length === 0 && <div className="pdf-page-loading">No pages to display.</div>}
      </div>
    </div>
  );
}
