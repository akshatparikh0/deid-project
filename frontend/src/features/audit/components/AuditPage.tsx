import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ApiError, exportJob, getAudit, getJob, reopenJob, resolveApiUrl } from '@/api/client';
import type { AuditRow, Job } from '@/api/types';
import { CategoryBadge } from '@/components/CategoryBadge';
import { StatusBadge } from '@/components/StatusBadge';
import { EmptyState, ErrorBanner, LoadingState } from '@/components/States';
import { formatDateTime, formatPercent } from '@/lib/format';
import { setActiveJob } from '@/stores/activeJob';
import { ModePill } from './ModePill';

export function AuditPage() {
  const { id } = useParams<{ id: string }>();
  const jobId = Number(id);
  const navigate = useNavigate();

  const [job, setJob] = useState<Job | null>(null);
  const [rows, setRows] = useState<AuditRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [reopening, setReopening] = useState(false);
  const [reopenError, setReopenError] = useState<string | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    Promise.all([getJob(jobId), getAudit(jobId)])
      .then(([jobRes, auditRes]) => {
        setJob(jobRes.job);
        setActiveJob(jobRes.job);
        setRows(auditRes.rows);
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.detail : 'Failed to load the audit trail.');
      })
      .finally(() => setLoading(false));
  }

  useEffect(load, [jobId]);

  async function onExportCsv() {
    setExporting(true);
    setExportError(null);
    try {
      const { files } = await exportJob(jobId, ['csv']);
      const csv = files.find((f) => f.format === 'csv');
      if (csv) window.open(resolveApiUrl(csv.url), '_blank', 'noreferrer');
    } catch (err) {
      setExportError(err instanceof ApiError ? err.detail : 'Failed to export the audit CSV.');
    } finally {
      setExporting(false);
    }
  }

  async function onReopen() {
    setReopening(true);
    setReopenError(null);
    try {
      await reopenJob(jobId);
      navigate(`/jobs/${jobId}/review`);
    } catch (err) {
      setReopenError(err instanceof ApiError ? err.detail : 'Failed to reopen this document.');
      setReopening(false);
    }
  }

  if (loading) return <LoadingState label="Loading audit trail…" />;
  if (error) return <ErrorBanner message={error} onRetry={load} />;
  if (!job || !rows) return null;

  return (
    <div>
      <div className="page-header">
        <div>
          <Link to="/queue" style={{ fontSize: 12, fontWeight: 500 }}>
            ← Document library
          </Link>
          <h1 className="page-title" style={{ marginTop: 5 }}>
            Audit record — {job.code}
          </h1>
          <p className="page-subtitle">
            Immutable log of every identifier found and the transformation applied. Values are
            hashed, never stored in clear text.
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
          <StatusBadge status={job.status} />
          {job.status === 'complete' ? (
            <button className="btn btn-sm" disabled={reopening} onClick={onReopen}>
              {reopening ? 'Reopening…' : 'Reopen for review'}
            </button>
          ) : (
            <Link to={`/jobs/${jobId}/review`} className="btn btn-sm">
              Continue review
            </Link>
          )}
          <button className="btn btn-sm btn-primary" onClick={onExportCsv} disabled={exporting}>
            {exporting ? 'Exporting…' : 'Export CSV'}
          </button>
        </div>
      </div>

      {exportError && <ErrorBanner message={exportError} />}
      {reopenError && <ErrorBanner message={reopenError} />}

      {rows.length === 0 ? (
        <div className="card">
          <EmptyState title="No audit rows yet" description="No entities have been recorded for this job." />
        </div>
      ) : (
        <div className="card" style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Entity</th>
                <th>Class</th>
                <th>Value hash</th>
                <th>Action</th>
                <th>Detector</th>
                <th>Conf.</th>
                <th>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.entity_code}>
                  <td className="mono">{row.entity_code}</td>
                  <td>
                    <CategoryBadge category={row.category} />
                  </td>
                  <td className="mono" style={{ fontSize: 12 }}>
                    {row.value_hash}
                  </td>
                  <td>
                    <ModePill mode={row.action} />
                  </td>
                  <td>{row.detector}</td>
                  <td>{formatPercent(row.confidence)}</td>
                  <td>{formatDateTime(row.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
