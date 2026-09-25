import type { CSSProperties } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import {
  ApiError,
  bulkUpdateEntities,
  completeJob,
  getDocument,
  getJob,
  getRules,
  updateEntity,
} from '@/api/client';
import type { Category, DocumentPayload, Entity, Job, Mode } from '@/api/types';
import { StatusBadge } from '@/components/StatusBadge';
import { ErrorBanner, LoadingState } from '@/components/States';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { paths } from '@/config/paths';
import { getDisplayThreshold } from '@/lib/threshold';
import { showToast } from '@/lib/toast';
import { setActiveJob } from '@/stores/activeJob';
import { EntityInspector } from './EntityInspector';
import { ExportModal } from './ExportModal';
import { PageImagePane } from './PageImagePane';

type PaneView = 'both' | 'original' | 'deidentified';

// A complete job's page images are already the finalized render (PHI is
// truly gone from the pixels, not just visually covered) — drawing the
// usual click-to-select entity overlays on top of it would just double up
// on (and, for a mask token, visually collide with) coverage that's
// already baked in, with no interactivity left to justify it.
const NO_ENTITIES_BY_PAGE = new Map<number, Entity[]>();

export function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const jobId = Number(id);
  const navigate = useNavigate();
  const location = useLocation();
  // Where "Close" goes back to depends on how this document was opened —
  // set by the caller's navigate(..., { state: { from, folder } }) — not just
  // whether the job has a batch, so opening the same job from the document
  // library always returns there (into the same folder) even if it came
  // from a batch upload.
  const openedState = location.state as { from?: 'status' | 'queue'; folder?: number | null } | null;
  const openedFrom = openedState?.from;

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

  async function handleComplete() {
    if (!job) return;
    setActionError(null);
    setLifecycleBusy(true);
    try {
      const { job: updated } = await completeJob(jobId);
      setJob(updated);
      setActiveJob(updated);
      showToast(`${updated.code} marked complete. Finalized, and the source document has been purged.`);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.detail : 'Failed to mark the job complete.');
    } finally {
      setLifecycleBusy(false);
    }
  }

  if (loading) return <LoadingState label="Loading document for review…" />;
  if (error) return <ErrorBanner message={error} onRetry={load} />;
  if (!job || !doc) return null;

  const isComplete = job.status === 'complete';
  // A complete job has no editable entities left (the source PDF is
  // permanently purged — see Job.purge_source_file) and only the
  // de-identified output actually matters at that point, so "Original"/
  // "Both" and the entity inspector have nothing left to offer.
  const showOriginal = !isComplete && paneView !== 'deidentified';
  const showDeid = isComplete || paneView !== 'original';
  const showInspector = !isComplete && inspectorOpen;
  const gridTemplateColumns = [
    showOriginal ? '1fr' : null,
    showDeid ? '1fr' : null,
    showInspector ? '320px' : null,
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
            <Link to={paths.jobRules.getHref(jobId)}>Rules</Link> ·{' '}
            <Link to={paths.jobAudit.getHref(jobId)}>Audit trail</Link>
          </div>
        </div>

        <div className="ml-auto flex flex-wrap justify-end gap-2.25">
          <Tabs value={isComplete ? 'deidentified' : paneView} onValueChange={(v) => setPaneView(v as PaneView)}>
            <TabsList>
              <TabsTrigger
                value="both"
                disabled={isComplete}
                title={isComplete ? 'Only the de-identified output is available once a document is complete.' : undefined}
              >
                Both
              </TabsTrigger>
              <TabsTrigger
                value="original"
                disabled={isComplete}
                title={isComplete ? 'The original is permanently removed once a document is complete.' : undefined}
              >
                Original
              </TabsTrigger>
              <TabsTrigger value="deidentified">Output</TabsTrigger>
            </TabsList>
          </Tabs>
          {!isComplete && (
            <Button variant="outline" size="sm" onClick={() => setInspectorOpen((v) => !v)}>
              {inspectorOpen ? 'Hide entities' : 'Show entities'}
            </Button>
          )}
          {!isComplete && (
            <Button variant="outline" size="sm" disabled={bulkBusy} onClick={() => handleBulk('redact')}>
              Redact all
            </Button>
          )}
          {!isComplete && (
            <Button variant="outline" size="sm" disabled={bulkBusy} onClick={() => handleBulk('mask')}>
              Mask all
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={() => setExportOpen(true)}>
            Export
          </Button>
          {isComplete ? (
            <div
              className="border-border flex items-center gap-2.25 border-l pl-2.25"
              title="This document is complete and its source file has been permanently removed. It cannot be reopened."
            >
              <StatusBadge status={job.status} />
            </div>
          ) : (
            <Button size="sm" disabled={lifecycleBusy} onClick={() => handleComplete()}>
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
              const dest =
                openedFrom === 'status' && job.batch != null
                  ? paths.uploadStatus.getHref(job.batch)
                  : paths.queue.getHref(openedState?.folder);
              setActiveJob(null);
              navigate(dest);
            }}
          >
            Close
          </Button>
        </div>
      </div>

      {actionError && <ErrorBanner message={actionError} />}

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
            entitiesByPage={isComplete ? NO_ENTITIES_BY_PAGE : entitiesByPage}
            ruleTokenByCategory={ruleTokens}
            selectedCode={selectedCode}
            onSelect={setSelectedCode}
            dimThreshold={dimThreshold}
          />
        )}
        {showInspector && (
          <EntityInspector
            entities={entities}
            selectedCode={selectedCode}
            onSelect={setSelectedCode}
            onModeChange={handleModeChange}
            busyId={busyId}
            threshold={dimThreshold}
          />
        )}
      </div>

      {exportOpen && <ExportModal jobId={jobId} onClose={() => setExportOpen(false)} />}
    </div>
  );
}
