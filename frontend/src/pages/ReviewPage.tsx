import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import {
  ApiError,
  bulkUpdateEntities,
  completeJob,
  getDocument,
  getJob,
  getRules,
  reopenJob,
  updateEntity,
} from '../api/client';
import type { Category, DocumentPayload, Entity, Job, Mode } from '../api/types';
import { PageImagePane } from '../components/PageImagePane';
import { EntityInspector } from '../components/EntityInspector';
import { ExportModal } from '../components/ExportModal';
import { StatusBadge } from '../components/StatusBadge';
import { ErrorBanner, LoadingState } from '../components/States';
import { setActiveJob } from '../lib/activeJob';
import { getDisplayThreshold } from '../lib/threshold';
import { showToast } from '../lib/toast';

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
      showToast(`${updated.code} marked complete. Finalized, verified, and the source document has been purged.`);
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
  const gridColumns = [
    showOriginal ? '1fr' : null,
    showDeid ? '1fr' : null,
    inspectorOpen ? '320px' : null,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 56px)' }}>
      <div
        className="card"
        style={{
          display: 'flex',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '12px 18px',
          padding: '14px 18px',
          marginBottom: 16,
        }}
      >
        <div style={{ minWidth: 220, maxWidth: 320 }}>
          <div
            style={{
              fontSize: 15.5,
              fontWeight: 600,
              letterSpacing: '-0.01em',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {job.filename}
          </div>
          <div className="mono page-subtitle" style={{ margin: 0, whiteSpace: 'nowrap' }}>
            {job.code} · {job.pages} page{job.pages === 1 ? '' : 's'} ·{' '}
            <Link to={`/jobs/${jobId}/rules`}>Rules</Link> · <Link to={`/jobs/${jobId}/audit`}>Audit trail</Link>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginLeft: 8 }}>
          <div style={{ fontSize: 11, color: 'var(--color-text-faint)', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
            Resolved
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <div className="progress-track">
              <div
                className={`progress-fill${unresolvedCount > 0 ? ' progress-fill-attention' : ''}`}
                style={{ width: `${progressPct}%` }}
              />
            </div>
            <span className="mono" style={{ fontSize: 12 }}>
              {resolvedCount} / {entities.length}
            </span>
          </div>
        </div>

        <div style={{ marginLeft: 'auto', display: 'flex', flexWrap: 'wrap', justifyContent: 'flex-end', gap: 9 }}>
          <div className="seg-group">
            {(
              [
                ['both', 'Both'],
                ['original', 'Original'],
                ['deidentified', 'Output'],
              ] as [PaneView, string][]
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                className={`seg-btn${paneView === key ? ' seg-btn-active' : ''}`}
                onClick={() => setPaneView(key)}
              >
                {label}
              </button>
            ))}
          </div>
          <button className="btn btn-sm" onClick={() => setInspectorOpen((v) => !v)}>
            {inspectorOpen ? 'Hide entities' : 'Show entities'}
          </button>
          <button className="btn btn-sm" disabled={bulkBusy || isComplete} onClick={() => handleBulk('redact')}>
            Redact all
          </button>
          <button className="btn btn-sm" disabled={bulkBusy || isComplete} onClick={() => handleBulk('mask')}>
            Mask all
          </button>
          <button className="btn btn-sm" onClick={() => setExportOpen(true)}>
            Export
          </button>
          {isComplete ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 9, paddingLeft: 9, borderLeft: '1px solid var(--color-border)' }}>
              <StatusBadge status={job.status} />
              <button className="btn btn-sm" disabled={lifecycleBusy} onClick={handleReopen}>
                Reopen
              </button>
            </div>
          ) : (
            <button
              className="btn btn-sm btn-primary"
              disabled={lifecycleBusy}
              title={unresolvedCount > 0 ? `${unresolvedCount} entities still need a decision` : undefined}
              onClick={() => handleComplete(false)}
            >
              Mark complete
            </button>
          )}
          <button
            className="btn btn-sm"
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
            style={{ marginLeft: 9, paddingLeft: 9, borderLeft: '1px solid var(--color-border)' }}
          >
            Close
          </button>
        </div>
      </div>

      {actionError && <ErrorBanner message={actionError} />}

      {confirmingComplete !== null && (
        <div className="error-banner" style={{ alignItems: 'center' }}>
          <span aria-hidden="true">&#9888;</span>
          <div style={{ flex: 1 }}>
            {confirmingComplete} entit{confirmingComplete === 1 ? 'y is' : 'ies are'} still kept
            as-is. Complete anyway?
          </div>
          <button className="btn btn-sm" onClick={() => setConfirmingComplete(null)}>
            Cancel
          </button>
          <button className="btn btn-sm btn-danger" onClick={() => handleComplete(true)}>
            Complete anyway
          </button>
        </div>
      )}

      <div className="review-grid" style={{ gridTemplateColumns: gridColumns }}>
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
