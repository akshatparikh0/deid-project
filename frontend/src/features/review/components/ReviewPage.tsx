import type { CSSProperties } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { TriangleAlert } from 'lucide-react';
import {
  ApiError,
  bulkUpdateEntities,
  completeJob,
  getDocument,
  getJob,
  getRules,
  reopenJob,
  updateEntity,
} from '@/api/client';
import type { Category, DocumentPayload, Entity, Job, Mode } from '@/api/types';
import { StatusBadge } from '@/components/StatusBadge';
import { ErrorBanner, LoadingState } from '@/components/States';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { cn } from '@/lib/utils';
import { getDisplayThreshold } from '@/lib/threshold';
import { showToast } from '@/lib/toast';
import { setActiveJob } from '@/stores/activeJob';
import { EntityInspector } from './EntityInspector';
import { ExportModal } from './ExportModal';
import { PageImagePane } from './PageImagePane';

type PaneView = 'both' | 'original' | 'deidentified';

export function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const jobId = Number(id);
  const navigate = useNavigate();
  const location = useLocation();
  // Where "Close" goes back to depends on how this document was opened —
  // set by the caller's navigate(..., { state: { from } }) — not just
  // whether the job has a batch, so opening the same job from the document
  // library always returns there even if it came from a batch upload.
  const openedFrom = (location.state as { from?: 'status' | 'queue' } | null)?.from;

  const [job, setJob] = useState<Job | null>(null);
  const [doc, setDoc] = useState<DocumentPayload | null>(null);
  const [ruleTokens, setRuleTokens] = useState<Partial<Record<Category, string>>>({});
  const [entities, setEntities] = useState<Entity[]>([]);
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [lifecycleBusy, setLifecycleBusy] = useState(false);
  const [confirmingComplete, setConfirmingComplete] = useState<number | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [paneView, setPaneView] = useState<PaneView>('both');
  const [inspectorOpen, setInspectorOpen] = useState(true);

  function load() {
    setLoading(true);
    setError(null);
    Promise.all([getJob(jobId), getDocument(jobId), getRules(jobId)])
      .then(([jobRes, docRes, rulesRes]) => {
        setJob(jobRes.job);
        setActiveJob(jobRes.job);
        setDoc(docRes);
        setEntities(docRes.entities);
        const tokens: Partial<Record<Category, string>> = {};
        rulesRes.rules.forEach((r) => {
          tokens[r.category] = r.token;
        });
        setRuleTokens(tokens);
        setSelectedCode((prev) => prev ?? docRes.entities[0]?.code ?? null);
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.detail : 'Failed to load this document for review.');
      })
      .finally(() => setLoading(false));
  }

  useEffect(load, [jobId]);

  const entitiesByPage = useMemo(() => {
    const map = new Map<number, Entity[]>();
    entities.forEach((e) => {
      const list = map.get(e.page);
      if (list) list.push(e);
      else map.set(e.page, [e]);
    });
    return map;
  }, [entities]);

  const unresolvedCount = useMemo(() => entities.filter((e) => e.mode === 'keep').length, [entities]);
  const dimThreshold = job ? getDisplayThreshold(jobId, job.confidence_threshold) : undefined;

  async function handleModeChange(entity: Entity, mode: Mode) {
    if (mode === entity.mode || job?.status === 'complete') return;
    setActionError(null);
    setBusyId(entity.id);
    const prev = entities;
    setEntities(entities.map((e) => (e.id === entity.id ? { ...e, mode } : e)));
    try {
      const { entity: updated } = await updateEntity(entity.id, mode);
      setEntities((cur) => cur.map((e) => (e.id === updated.id ? updated : e)));
    } catch (err) {
      setEntities(prev);
      setActionError(err instanceof ApiError ? err.detail : `Failed to update ${entity.code}.`);
    } finally {
      setBusyId(null);
    }
  }

  async function handleBulk(mode: Mode) {
    setActionError(null);
    setBulkBusy(true);
    try {
      const { entities: updated } = await bulkUpdateEntities(jobId, { mode });
      setEntities(updated);
      showToast(`All ${updated.length} entities set to ${mode === 'redact' ? 'redact' : 'mask'}.`);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.detail : 'Bulk update failed.');
    } finally {
      setBulkBusy(false);
    }
  }

  async function handleComplete(force?: boolean) {
    if (!job) return;
    setActionError(null);
    setLifecycleBusy(true);
    try {
      const { job: updated } = await completeJob(jobId, force);
      setJob(updated);
      setActiveJob(updated);
      setConfirmingComplete(null);
      showToast(`${updated.code} marked complete. Source document scheduled for purge in 24 h.`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const count = (err.body?.unresolved_count as number | undefined) ?? unresolvedCount;
        setConfirmingComplete(count);
      } else {
        setActionError(err instanceof ApiError ? err.detail : 'Failed to mark the job complete.');
      }
    } finally {
      setLifecycleBusy(false);
    }
  }

  async function handleReopen() {
    setActionError(null);
    setLifecycleBusy(true);
    try {
      const { job: updated } = await reopenJob(jobId);
      setJob(updated);
      setActiveJob(updated);
      showToast(`${updated.code} reopened for review.`);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.detail : 'Failed to reopen the job.');
    } finally {
      setLifecycleBusy(false);
    }
  }

  if (loading) return <LoadingState label="Loading document for review…" />;
  if (error) return <ErrorBanner message={error} onRetry={load} />;
  if (!job || !doc) return null;

  const isComplete = job.status === 'complete';
  const resolvedCount = entities.length - unresolvedCount;
  const progressPct = entities.length === 0 ? 0 : Math.round((resolvedCount / entities.length) * 100);
  const showOriginal = paneView !== 'deidentified';
  const showDeid = paneView !== 'original';
  const gridTemplateColumns = [
    showOriginal ? '1fr' : null,
    showDeid ? '1fr' : null,
    inspectorOpen ? '320px' : null,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className="flex h-[calc(100vh-56px)] flex-col">
      <div className="bg-card border-border mb-4 flex flex-wrap items-center gap-x-4.5 gap-y-3 rounded-md border px-4.5 py-3.5">
        <div className="min-w-55 max-w-80">
          <div className="overflow-hidden text-[15.5px] font-semibold tracking-[-0.01em] text-ellipsis whitespace-nowrap">
            {job.filename}
          </div>
          <div className="text-muted-foreground font-mono text-[13.5px] whitespace-nowrap">
            {job.code} · {job.pages} page{job.pages === 1 ? '' : 's'} ·{' '}
            <Link to={`/jobs/${jobId}/rules`}>Rules</Link> · <Link to={`/jobs/${jobId}/audit`}>Audit trail</Link>
          </div>
        </div>

        <div className="ml-2 flex flex-col gap-1.25">
          <div className="text-muted-foreground text-[11px] tracking-[0.05em] uppercase">Resolved</div>
          <div className="flex items-center gap-2.25">
            <div className="bg-muted h-1.25 w-37.5 overflow-hidden rounded-full">
              <div
                className={cn(
                  'h-full rounded-full transition-[width] duration-200',
                  unresolvedCount > 0 ? 'bg-status-warning' : 'bg-status-success',
                )}
                style={{ width: `${progressPct}%` }}
              />
            </div>
            <span className="font-mono text-xs">
              {resolvedCount} / {entities.length}
            </span>
          </div>
        </div>

        <div className="ml-auto flex flex-wrap justify-end gap-2.25">
          <Tabs value={paneView} onValueChange={(v) => setPaneView(v as PaneView)}>
            <TabsList>
              <TabsTrigger value="both">Both</TabsTrigger>
              <TabsTrigger value="original">Original</TabsTrigger>
              <TabsTrigger value="deidentified">Output</TabsTrigger>
            </TabsList>
          </Tabs>
          <Button variant="outline" size="sm" onClick={() => setInspectorOpen((v) => !v)}>
            {inspectorOpen ? 'Hide entities' : 'Show entities'}
          </Button>
          <Button variant="outline" size="sm" disabled={bulkBusy || isComplete} onClick={() => handleBulk('redact')}>
            Redact all
          </Button>
          <Button variant="outline" size="sm" disabled={bulkBusy || isComplete} onClick={() => handleBulk('mask')}>
            Mask all
          </Button>
          <Button variant="outline" size="sm" onClick={() => setExportOpen(true)}>
            Export
          </Button>
          {isComplete ? (
            <div className="border-border flex items-center gap-2.25 border-l pl-2.25">
              <StatusBadge status={job.status} />
              <Button variant="outline" size="sm" disabled={lifecycleBusy} onClick={handleReopen}>
                Reopen
              </Button>
            </div>
          ) : (
            <Button
              size="sm"
              disabled={lifecycleBusy}
              title={unresolvedCount > 0 ? `${unresolvedCount} entities still need a decision` : undefined}
              onClick={() => handleComplete(false)}
            >
              Mark complete
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            className="border-border ml-2.25 border-l pl-2.25"
            title={
              openedFrom === 'status' && job.batch != null
                ? 'Close file and return to upload status'
                : 'Close file and return to document library'
            }
            onClick={() => {
              const dest = openedFrom === 'status' && job.batch != null ? `/uploads/${job.batch}/status` : '/queue';
              setActiveJob(null);
              navigate(dest);
            }}
          >
            Close
          </Button>
        </div>
      </div>

      {actionError && <ErrorBanner message={actionError} />}

      {confirmingComplete !== null && (
        <div className="bg-status-danger-bg text-destructive border-destructive/20 mb-4.5 flex items-center gap-2.5 rounded-md border px-3.5 py-3 text-[13px]">
          <TriangleAlert className="size-4 shrink-0" aria-hidden="true" />
          <div className="flex-1">
            {confirmingComplete} entit{confirmingComplete === 1 ? 'y is' : 'ies are'} still kept
            as-is. Complete anyway?
          </div>
          <Button variant="outline" size="sm" onClick={() => setConfirmingComplete(null)}>
            Cancel
          </Button>
          <Button variant="destructive" size="sm" onClick={() => handleComplete(true)}>
            Complete anyway
          </Button>
        </div>
      )}

      <div
        className="grid min-h-0 flex-1 grid-cols-[var(--review-grid-cols)] gap-4 max-lg:h-auto max-lg:grid-cols-1"
        style={{ '--review-grid-cols': gridTemplateColumns } as CSSProperties}
      >
        {showOriginal && (
          <PageImagePane
            title="Original — PHI highlighted"
            variant="original"
            pages={doc.pages}
            entitiesByPage={entitiesByPage}
            ruleTokenByCategory={ruleTokens}
            selectedCode={selectedCode}
            onSelect={setSelectedCode}
            dimThreshold={dimThreshold}
          />
        )}
        {showDeid && (
          <PageImagePane
            title="De-identified output"
            variant="deidentified"
            pages={doc.pages}
            entitiesByPage={entitiesByPage}
            ruleTokenByCategory={ruleTokens}
            selectedCode={selectedCode}
            onSelect={setSelectedCode}
            dimThreshold={dimThreshold}
          />
        )}
        {inspectorOpen && (
          <EntityInspector
            entities={entities}
            selectedCode={selectedCode}
            onSelect={setSelectedCode}
            onModeChange={handleModeChange}
            busyId={busyId}
            threshold={dimThreshold}
            readOnly={isComplete}
          />
        )}
      </div>

      {exportOpen && <ExportModal jobId={jobId} onClose={() => setExportOpen(false)} />}
    </div>
  );
}
