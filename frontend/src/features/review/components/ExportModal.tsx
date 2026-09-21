import { useState } from 'react';
import { ApiError, exportJob, resolveApiUrl } from '@/api/client';
import type { ExportFile, ExportFormat } from '@/api/types';
import { ErrorBanner } from '@/components/States';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { showToast } from '@/lib/toast';

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
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-105">
        <DialogHeader>
          <DialogTitle className="font-serif text-[19px]">Export job</DialogTitle>
          <DialogDescription>
            Generate a de-identified PDF, the audit CSV, and/or the entity manifest JSON.
          </DialogDescription>
        </DialogHeader>

        {error && <ErrorBanner message={error} />}

        {!files && (
          <div className="flex flex-col gap-2.5">
            {FORMATS.map((f) => (
              <label
                key={f.value}
                className="border-border flex cursor-pointer items-start gap-2.5 rounded-sm border px-3 py-2.5"
              >
                <Checkbox
                  className="mt-0.5"
                  checked={selected.has(f.value)}
                  onCheckedChange={() => toggle(f.value)}
                />
                <span>
                  <span className="block font-semibold">{f.label}</span>
                  <span className="text-muted-foreground text-[13.5px]">{f.description}</span>
                </span>
              </label>
            ))}
          </div>
        )}

        {files && (
          <div className="flex flex-col gap-2">
            {files.map((file) => (
              <Button key={file.format} variant="outline" className="h-auto justify-between" asChild>
                <a href={resolveApiUrl(file.url)} target="_blank" rel="noreferrer">
                  <span>
                    Download {file.filename} <span className="text-muted-foreground">({file.format})</span>
                  </span>
                  <span aria-hidden="true">&#8595;</span>
                </a>
              </Button>
            ))}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {files ? 'Close' : 'Cancel'}
          </Button>
          {!files && (
            <Button onClick={onGenerate} disabled={submitting}>
              {submitting ? 'Generating…' : 'Generate export'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
