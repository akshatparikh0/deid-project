import { useEffect, useRef, useState } from 'react';
import type { DragEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { FileText, X } from 'lucide-react';
import { ApiError, createUploadBatch, listFolders } from '@/api/client';
import type { Mode } from '@/api/types';
import { PageHeader } from '@/components/Layout';
import { EmptyState, ErrorBanner, LoadingState } from '@/components/States';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { paths } from '@/config/paths';
import { isPatientFolder } from '@/lib/folders';
import { showToast } from '@/lib/toast';
import { cn } from '@/lib/utils';
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
  const libraryHref = paths.queue.getHref(folder);
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
  // React has no typed JSX prop for it — it has to be set on the DOM node
  // itself. A callback ref (rather than an effect) ensures it's applied the
  // moment the input actually mounts, since this page's early-return loading
  // state means the input isn't present on first render.
  function setFolderInputRef(el: HTMLInputElement | null) {
    folderInputRef.current = el;
    el?.setAttribute('webkitdirectory', '');
  }

  function fileKey(f: File): string {
    const relativePath = (f as File & { webkitRelativePath?: string }).webkitRelativePath;
    return relativePath ? `${relativePath}:${f.size}` : `${f.name}:${f.size}`;
  }

  function pickFiles(list: FileList | File[] | null | undefined) {
    if (!list) return;
    const incoming = Array.from(list);
    const validOnes = incoming.filter(isPdf);
    const skippedNames = incoming.filter((f) => !isPdf(f)).map((f) => f.name);

    setFiles((prev) => {
      const seen = new Set(prev.map(fileKey));
      const merged = [...prev];
      for (const f of validOnes) {
        const key = fileKey(f);
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
      navigate(paths.uploadStatus.getHref(batch.id));
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
      <div className="flex justify-center">
        <div className="w-full max-w-170">
          <PageHeader
            title="New de-identification job"
            subtitle="Files are processed in an isolated enclave. Source documents are purged as soon as the job is marked complete."
          />
          <Card className="p-6">
            <EmptyState
              title="Choose a patient folder first"
              description="Documents can only be uploaded inside a patient folder. Open a patient folder in the document library, then upload from there."
              action={
                <Button asChild>
                  <Link to="/queue">Go to document library</Link>
                </Button>
              }
            />
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-center">
      <div className="w-full max-w-170">
        <PageHeader
          title="New de-identification job"
          subtitle="Files are processed in an isolated enclave. Source documents are purged as soon as the job is marked complete."
        />

        {error && <ErrorBanner message={error} />}
        {skipped.length > 0 && (
          <ErrorBanner
            message={`Skipped ${skipped.length} non-PDF file${skipped.length === 1 ? '' : 's'}: ${skipped.join(', ')}`}
          />
        )}

        <Card className="p-6">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            className={cn(
              'cursor-pointer rounded-md border-1.5 border-dashed px-6 py-11 text-center transition-colors duration-100',
              dragging ? 'border-status-success bg-status-success-bg/30' : 'border-border bg-background',
            )}
          >
            <input
              ref={inputRef}
              type="file"
              accept="application/pdf,.pdf"
              multiple
              hidden
              onChange={(e) => pickFiles(e.target.files)}
            />
            <input ref={setFolderInputRef} type="file" multiple hidden onChange={(e) => pickFiles(e.target.files)} />
            <FileText className="text-muted-foreground mx-auto mb-2.5 size-9" strokeWidth={1.25} aria-hidden="true" />
            {files.length > 0 ? (
              <>
                <div className="text-sm font-medium">
                  {files.length} file{files.length === 1 ? '' : 's'} selected
                </div>
                <div className="text-muted-foreground font-mono mt-1 text-[13.5px]">click or drop to add more</div>
              </>
            ) : (
              <>
                <div className="text-sm font-medium">Drop PDFs here, or browse</div>
                <div className="text-muted-foreground font-mono mt-1 text-[13.5px]">
                  PDF · up to 400 pages · 50 MB each
                </div>
              </>
            )}
          </div>

          <div className="mt-3.5 flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                inputRef.current?.click();
              }}
            >
              Choose files
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                folderInputRef.current?.click();
              }}
            >
              Choose folder
            </Button>
          </div>

          {files.length > 0 && (
            <ul className="border-border mt-3.5 max-h-55 list-none overflow-y-auto rounded-sm border p-0">
              {files.map((f, i) => (
                <li
                  key={`${f.name}:${f.size}:${i}`}
                  className="border-border flex items-center gap-2.5 border-b px-3 py-2 text-[13px] last:border-b-0"
                >
                  <span className="flex-1 overflow-hidden text-ellipsis whitespace-nowrap">{f.name}</span>
                  <span className="text-muted-foreground font-mono flex-none text-[11.5px]">
                    {(f.size / 1024).toFixed(0)} KB
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Remove ${f.name}`}
                    onClick={() => removeFile(i)}
                  >
                    <X className="size-3.5" />
                  </Button>
                </li>
              ))}
            </ul>
          )}

          <div className="mt-5">
            <div className="mb-0.5 text-[13px] font-medium">Transformation types</div>
            <p className="text-muted-foreground mt-0 mb-2.5 text-[13.5px]">
              Every identifier class defaults to Mask. The default action for each class can be
              changed on the next step, and any single entity can be overridden during review.
            </p>
            <div className="grid grid-cols-3 gap-2.5">
              {PRESETS.map((p) => (
                <Card key={p.mode} className="flex flex-col gap-1.5 p-3.25">
                  <div className="flex items-center gap-2">
                    <span className="bg-muted-foreground/40 size-2.25 shrink-0 rounded-full" />
                    <span className="text-[13.5px] font-semibold">{p.label}</span>
                  </div>
                  <div className="text-muted-foreground text-[12px] leading-relaxed">{p.description}</div>
                  <div className="text-muted-foreground font-mono text-[11px]">{p.sample}</div>
                  {p.reIdentifiable && (
                    <span className="bg-status-info-bg text-status-info font-mono self-start rounded-full px-1.75 py-0.5 text-[10px] tracking-[0.08em]">
                      RE-IDENTIFIABLE
                    </span>
                  )}
                </Card>
              ))}
            </div>
          </div>

          <div className="mt-6 flex gap-2.5">
            <Button disabled={files.length === 0 || submitting} onClick={onSubmit}>
              {submitting
                ? 'Uploading…'
                : files.length === 0
                  ? 'Scan for PHI'
                  : `Scan ${files.length} file${files.length === 1 ? '' : 's'}`}
            </Button>
            <Button variant="outline" disabled={submitting} onClick={() => navigate(libraryHref)}>
              Cancel
            </Button>
          </div>
        </Card>
      </div>
    </div>
  );
}
