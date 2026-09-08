import { useState } from 'react';
import { ApiError, exportJob, resolveApiUrl } from '../api/client';
import type { ExportFile, ExportFormat } from '../api/types';
import { showToast } from '../lib/toast';
import { ErrorBanner } from './States';

const FORMATS: { value: ExportFormat; label: string; description: string }[] = [
  { value: 'pdf', label: 'De-identified PDF', description: 'Reconstructed document with all handling applied.' },
  { value: 'csv', label: 'Audit CSV', description: 'One row per entity: hash, action, detector, confidence.' },
  { value: 'json', label: 'Entity manifest (JSON)', description: 'Full structured record of every detected entity.' },
];

export function ExportModal({ jobId, onClose }: { jobId: number; onClose: () => void }) {
  const [selected, setSelected] = useState<Set<ExportFormat>>(new Set(['pdf', 'csv', 'json']));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [files, setFiles] = useState<ExportFile[] | null>(null);

  function toggle(format: ExportFormat) {
    const next = new Set(selected);
    if (next.has(format)) next.delete(format);
    else next.add(format);
    setSelected(next);
  }

  async function onGenerate() {
    if (selected.size === 0) {
      setError('Choose at least one export format.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await exportJob(jobId, Array.from(selected));
      setFiles(res.files);
      showToast(`Package generated — ${res.files.length} file${res.files.length === 1 ? '' : 's'} written to the compliance vault.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Export failed. Please try again.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <h2 className="modal-title">Export job</h2>
        <p className="page-subtitle">
          Generate a de-identified PDF, the audit CSV, and/or the entity manifest JSON.
        </p>

        {error && <ErrorBanner message={error} />}

        {!files && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 14 }}>
            {FORMATS.map((f) => (
              <label
                key={f.value}
                style={{
                  display: 'flex',
                  gap: 10,
                  alignItems: 'flex-start',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '10px 12px',
                  cursor: 'pointer',
                }}
              >
                <input
                  type="checkbox"
                  checked={selected.has(f.value)}
                  onChange={() => toggle(f.value)}
                  style={{ marginTop: 2 }}
                />
                <span>
                  <span style={{ fontWeight: 600, display: 'block' }}>{f.label}</span>
                  <span className="page-subtitle" style={{ margin: 0 }}>
                    {f.description}
                  </span>
                </span>
              </label>
            ))}
          </div>
        )}

        {files && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 14 }}>
            {files.map((file) => (
              <a
                key={file.format}
                href={resolveApiUrl(file.url)}
                target="_blank"
                rel="noreferrer"
                className="btn"
                style={{ justifyContent: 'space-between' }}
              >
                <span>
                  Download {file.filename} <span className="page-subtitle">({file.format})</span>
                </span>
                <span aria-hidden="true">&#8595;</span>
              </a>
            ))}
          </div>
        )}

        <div className="modal-actions">
          <button className="btn" onClick={onClose}>
            {files ? 'Close' : 'Cancel'}
          </button>
          {!files && (
            <button className="btn btn-primary" onClick={onGenerate} disabled={submitting}>
              {submitting ? 'Generating…' : 'Generate export'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
