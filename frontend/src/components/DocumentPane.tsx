import { useEffect, useRef } from 'react';
import type { Category, DocumentBlock, Entity } from '../api/types';
import { categoryColor } from '../lib/categories';

function hexToRgba(hex: string, alpha: number): string {
  const m = hex.replace('#', '');
  const r = parseInt(m.substring(0, 2), 16);
  const g = parseInt(m.substring(2, 4), 16);
  const b = parseInt(m.substring(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

const BLOCK_CLASS: Record<DocumentBlock['type'], string> = {
  title: 'doc-block-title',
  sub: 'doc-block-sub',
  h: 'doc-block-h',
  p: 'doc-block-p',
};

export function DocumentPane({
  title,
  variant,
  blocks,
  entitiesByCode,
  ruleTokenByCategory,
  selectedCode,
  onSelect,
  dimThreshold,
}: {
  title: string;
  variant: 'original' | 'deidentified';
  blocks: DocumentBlock[];
  entitiesByCode: Map<string, Entity>;
  ruleTokenByCategory: Partial<Record<Category, string>>;
  selectedCode: string | null;
  onSelect: (code: string) => void;
  dimThreshold?: number;
}) {
  let lastPage: number | null = null;
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!selectedCode || !bodyRef.current) return;
    const el = bodyRef.current.querySelector(`[data-entity-code="${selectedCode}"]`);
    el?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [selectedCode]);

  return (
    <div className="card doc-pane">
      <div className="doc-pane-header">{title}</div>
      <div className="doc-pane-body" ref={bodyRef}>
        {blocks.map((block) => {
          const showPageBreak = lastPage !== null && block.page !== lastPage;
          lastPage = block.page;
          return (
            <div key={block.index}>
              {showPageBreak && <div className="doc-page-break">Page {block.page}</div>}
              {block.index === 0 && <div className="doc-page-break">Page {block.page}</div>}
              <div className={`doc-block ${BLOCK_CLASS[block.type]}`}>
                {block.parts.map((part, i) => {
                  if ('text' in part) {
                    return <span key={i}>{part.text}</span>;
                  }
                  const entity = entitiesByCode.get(part.entity);
                  if (!entity) return <span key={i}>{part.entity}</span>;
                  const dim = dimThreshold != null && entity.confidence < dimThreshold;
                  const selected = entity.code === selectedCode;

                  if (variant === 'original') {
                    const color = categoryColor(entity.category);
                    const alpha = dim ? 0.08 : selected ? 0.22 : 0.1;
                    return (
                      <span
                        key={i}
                        onClick={() => onSelect(entity.code)}
                        data-entity-code={entity.code}
                        title={`${entity.code} · ${Math.round(entity.confidence * 100)}% confidence`}
                        className="doc-span"
                        style={{
                          background: hexToRgba(color, alpha),
                          borderBottom: `2px solid ${color}`,
                          outline: selected ? `1px solid ${color}` : 'none',
                          opacity: dim ? 0.6 : 1,
                        }}
                      >
                        {entity.value}
                      </span>
                    );
                  }

                  const content =
                    entity.mode === 'redact'
                      ? entity.value
                      : entity.mode === 'mask'
                        ? (ruleTokenByCategory[entity.category] ?? `[${entity.category.toUpperCase()}]`)
                        : entity.mode === 'pseudo'
                          ? entity.surrogate_value || entity.value
                          : entity.value;

                  return (
                    <span
                      key={i}
                      onClick={() => onSelect(entity.code)}
                      data-entity-code={entity.code}
                      title={`${entity.code} · ${entity.mode}`}
                      className={`doc-span doc-span-${entity.mode}${selected ? ' doc-span-selected' : ''}`}
                      style={{ opacity: dim ? 0.6 : 1 }}
                    >
                      {content}
                    </span>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
