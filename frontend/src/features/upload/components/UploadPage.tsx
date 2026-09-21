import { useEffect, useRef, useState } from 'react';
import type { DragEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ApiError, createUploadBatch, listFolders } from '@/api/client';
import type { Mode } from '@/api/types';
import { PageHeader } from '@/components/Layout';
import { EmptyState, ErrorBanner, LoadingState } from '@/components/States';
import { isPatientFolder } from '@/lib/folders';
import { showToast } from '@/lib/toast';
import { setActiveBatch } from '@/stores/activeJob';

const PRESETS: {
  mode: Mode;
  label: string;
  description: string;
  sample: string;
  reIdentifiable?: boolean;
}[] = [
  {
    mode: 'redact',
    label: 'Redact',
    description:
      'A black bar is burned over the value. Nothing recoverable remains in the output PDF or its text layer.',
    sample: '03/14/1961 → ██████████',
  },
  {
    mode: 'mask',
    label: 'Mask',
    description: 'The value is replaced by a placeholder token. Document structure and readability are preserved.',
    sample: '03/14/1961 → [DATE]',
  },
  {
    mode: 'pseudo',
    label: 'Pseudonymize',
    description:
      'A consistent surrogate replaces the value everywhere it appears. The mapping is retained so the set can be re-identified under a separate authorization.',
    sample: '03/14/1961 → 07/02/1961',
    reIdentifiable: true,
  },
];

const DEFAULT_PRESET: Mode = 'mask';

function isPdf(f: File): boolean {
  return f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf');
}

export function UploadPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [skipped, setSkipped] = useState<string[]>([]);
  const [dragging, setDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const folderParam = searchParams.get('folder');
  const folder = folderParam ? Number(folderParam) : null;
  const libraryHref = folder ? `/queue?folder=${folder}` : '/queue';
  const [folderValid, setFolderValid] = useState<boolean | null>(null);

  useEffect(() => {
    if (folder === null) {
      setFolderValid(false);
      return;
    }
    listFolders()
      .then((res) => setFolderValid(isPatientFolder(res.folders, folder)))
      .catch(() => setFolderValid(false));
  }, [folder]);

  // Browsers only expose folder-select via this non-standard attribute, and
  // React has no typed JSX prop for it — it has to be set on the DOM node.
  useEffect(() => {
    folderInputRef.current?.setAttribute('webkitdirectory', '');
  }, []);

  function pickFiles(list: FileList | File[] | null | undefined) {
    if (!list) return;
    const incoming = Array.from(list);
    const validOnes = incoming.filter(isPdf);
    const skippedNames = incoming.filter((f) => !isPdf(f)).map((f) => f.name);

    setFiles((prev) => {
      const seen = new Set(prev.map((f) => `${f.name}:${f.size}`));
      const merged = [...prev];
      for (const f of validOnes) {
        const key = `${f.name}:${f.size}`;
        if (!seen.has(key)) {
          seen.add(key);
          merged.push(f);
        }
      }
      return merged;
    });
    setSkipped(skippedNames);
    if (validOnes.length > 0) setError(null);
  }

  function removeFile(index: number) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    pickFiles(e.dataTransfer.files);
  }

  async function onSubmit() {
    if (files.length === 0) {
      setError('Choose at least one PDF to scan first.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const { batch, rejected } = await createUploadBatch({ files, preset: DEFAULT_PRESET, folder: folder! });
      if (rejected.length > 0) {
        showToast(`${batch.total} file(s) queued for scanning — ${rejected.length} skipped (not a valid PDF).`);
      } else {
        showToast(`${batch.total} file(s) queued for scanning.`);
      }
      setActiveBatch(batch.id);
      navigate(`/uploads/${batch.id}/status`);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Upload failed. Please try again.');
      setSubmitting(false);
    }
  }

  if (folderValid === null) {
    return <LoadingState label="Checking folder…" />;
  }

  if (!folderValid) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center' }}>
        <div style={{ width: '100%', maxWidth: 680 }}>
          <PageHeader
            title="New de-identification job"
            subtitle="Files are processed in an isolated enclave. Source documents are purged after export."
          />
          <div className="card">
            <EmptyState
              title="Choose a patient folder first"
              description="Documents can only be uploaded inside a patient folder. Open a patient folder in the document library, then upload from there."
              action={
                <Link to="/queue" className="btn btn-primary">
                  Go to document library
                </Link>
              }
            />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', justifyContent: 'center' }}>
      <div style={{ width: '100%', maxWidth: 680 }}>
        <PageHeader
          title="New de-identification job"
          subtitle="Files are processed in an isolated enclave. Source documents are purged after export."
        />

        {error && <ErrorBanner message={error} />}
        {skipped.length > 0 && (
          <ErrorBanner
            message={`Skipped ${skipped.length} non-PDF file${skipped.length === 1 ? '' : 's'}: ${skipped.join(', ')}`}
          />
        )}

        <div className="card" style={{ padding: 24 }}>
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            style={{
              border: `1.5px dashed ${dragging ? 'var(--color-success)' : '#c9c4b8'}`,
              borderRadius: 'var(--radius-md)',
              background: dragging ? '#fcfdfc' : '#fff',
              padding: '44px 24px',
              textAlign: 'center',
              cursor: 'pointer',
              transition: 'border-color 0.12s ease, background 0.12s ease',
            }}
          >
            <input
              ref={inputRef}
              type="file"
              accept="application/pdf,.pdf"
              multiple
              hidden
              onChange={(e) => pickFiles(e.target.files)}
            />
            <input
              ref={folderInputRef}
              type="file"
              multiple
              hidden
              onChange={(e) => pickFiles(e.target.files)}
            />
            <div className="upload-doc-glyph" aria-hidden="true">
              <span style={{ top: 12 }} />
              <span style={{ top: 20 }} />
              <span style={{ top: 28, right: 16 }} />
            </div>
            {files.length > 0 ? (
              <>
                <div style={{ fontSize: 14, fontWeight: 500 }}>
                  {files.length} file{files.length === 1 ? '' : 's'} selected
                </div>
                <div className="page-subtitle" style={{ marginTop: 4, fontFamily: 'var(--font-mono)' }}>
                  click or drop to add more
                </div>
              </>
            ) : (
              <>
                <div style={{ fontSize: 14, fontWeight: 500 }}>Drop PDFs here, or browse</div>
                <div className="page-subtitle" style={{ marginTop: 4, fontFamily: 'var(--font-mono)' }}>
                  PDF · up to 400 pages · 50 MB each
                </div>
              </>
            )}
          </div>

          <div style={{ marginTop: 14, display: 'flex', gap: 8 }}>
            <button
              type="button"
              className="btn btn-sm"
              onClick={(e) => {
                e.stopPropagation();
                inputRef.current?.click();
              }}
            >
              Choose files
            </button>
            <button
              type="button"
              className="btn btn-sm"
              onClick={(e) => {
                e.stopPropagation();
                folderInputRef.current?.click();
              }}
            >
              Choose folder
            </button>
          </div>

          {files.length > 0 && (
            <ul className="staged-file-list">
              {files.map((f, i) => (
                <li key={`${f.name}:${f.size}:${i}`} className="staged-file-row">
                  <span className="staged-file-name">{f.name}</span>
                  <span className="mono staged-file-size">{(f.size / 1024).toFixed(0)} KB</span>
                  <button
                    type="button"
                    className="btn btn-sm btn-ghost"
                    aria-label={`Remove ${f.name}`}
                    onClick={() => removeFile(i)}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}

          <div style={{ marginTop: 20 }}>
            <div className="field-label" style={{ marginBottom: 2 }}>
              Transformation types
            </div>
            <p className="page-subtitle" style={{ marginTop: 0, marginBottom: 10 }}>
              Every identifier class defaults to Mask. The default action for each class can be
              changed on the next step, and any single entity can be overridden during review.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
              {PRESETS.map((p) => (
                <div
                  key={p.mode}
                  className="card"
                  style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: 13 }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span
                      style={{ width: 9, height: 9, borderRadius: '50%', background: '#d3cfc4' }}
                    />
                    <span style={{ fontSize: 13.5, fontWeight: 600 }}>{p.label}</span>
                  </div>
                  <div style={{ fontSize: 12, lineHeight: 1.5, color: '#7a7e84' }}>{p.description}</div>
                  <div className="mono" style={{ fontSize: 11, color: 'var(--color-text-faint)' }}>
                    {p.sample}
                  </div>
                  {p.reIdentifiable && (
                    <span
                      className="mono"
                      style={{
                        fontSize: 10,
                        letterSpacing: '0.08em',
                        color: 'var(--color-accent)',
                        background: '#edf2f8',
                        borderRadius: 999,
                        padding: '2px 7px',
                        alignSelf: 'flex-start',
                      }}
                    >
                      RE-IDENTIFIABLE
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div style={{ marginTop: 24, display: 'flex', gap: 10 }}>
            <button className="btn btn-primary" disabled={files.length === 0 || submitting} onClick={onSubmit}>
              {submitting
                ? 'Uploading…'
                : files.length === 0
                  ? 'Scan for PHI'
                  : `Scan ${files.length} file${files.length === 1 ? '' : 's'}`}
            </button>
            <button className="btn" disabled={submitting} onClick={() => navigate(libraryHref)}>
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
