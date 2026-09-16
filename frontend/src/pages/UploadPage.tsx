import { useEffect, useRef, useState } from 'react';
import type { DragEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ApiError, applyRules, createJob, listFolders } from '../api/client';
import type { Mode } from '../api/types';
import { PageHeader } from '../components/Layout';
import { EmptyState, ErrorBanner, LoadingState } from '../components/States';
import { isPatientFolder } from '../lib/folders';
import { showToast } from '../lib/toast';

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

export function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
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

  function pickFile(f: File | undefined | null) {
    if (!f) return;
    if (f.type !== 'application/pdf' && !f.name.toLowerCase().endsWith('.pdf')) {
      setError('Only PDF files are supported.');
      return;
    }
    setError(null);
    setFile(f);
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    pickFile(e.dataTransfer.files?.[0]);
  }

  async function onSubmit() {
    if (!file) {
      setError('Choose a PDF to scan first.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const { job } = await createJob({ file, preset: DEFAULT_PRESET, folder });
      if (job.status === 'failed') {
        setError(job.error_message || 'This PDF could not be processed.');
        setSubmitting(false);
        return;
      }
      // The folder's config rules were already confirmed before upload, so apply
      // them straight away instead of stopping on a redundant per-job rules step.
      await applyRules(job.id);
      showToast(`Scan complete — ${job.entity_count} identifiers in ${job.class_count} classes.`);
      navigate(`/jobs/${job.id}/review`);
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
              hidden
              onChange={(e) => pickFile(e.target.files?.[0])}
            />
            <div className="upload-doc-glyph" aria-hidden="true">
              <span style={{ top: 12 }} />
              <span style={{ top: 20 }} />
              <span style={{ top: 28, right: 16 }} />
            </div>
            {file ? (
              <>
                <div style={{ fontSize: 14, fontWeight: 500 }}>{file.name}</div>
                <div className="page-subtitle" style={{ marginTop: 4, fontFamily: 'var(--font-mono)' }}>
                  {(file.size / 1024).toFixed(0)} KB — click or drop to replace
                </div>
              </>
            ) : (
              <>
                <div style={{ fontSize: 14, fontWeight: 500 }}>Drop a PDF here, or browse</div>
                <div className="page-subtitle" style={{ marginTop: 4, fontFamily: 'var(--font-mono)' }}>
                  PDF · up to 400 pages · 50 MB
                </div>
              </>
            )}
          </div>

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
            <button className="btn btn-primary" disabled={!file || submitting} onClick={onSubmit}>
              {submitting ? 'Scanning…' : 'Scan for PHI'}
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
