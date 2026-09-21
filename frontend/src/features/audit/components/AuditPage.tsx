import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ApiError, exportJob, getAudit, getJob, reopenJob, resolveApiUrl } from '@/api/client';
import type { AuditRow, Job } from '@/api/types';
import { CategoryBadge } from '@/components/CategoryBadge';
import { PageHeader } from '@/components/Layout';
import { StatusBadge } from '@/components/StatusBadge';
import { EmptyState, ErrorBanner, LoadingState } from '@/components/States';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
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
      <Link to="/queue" className="mb-1.5 inline-block text-xs font-medium text-muted-foreground hover:text-foreground">
        ← Document library
      </Link>
      <PageHeader
        title={`Audit record — ${job.code}`}
        subtitle="Immutable log of every identifier found and the transformation applied. Values are hashed, never stored in clear text."
        actions={
          <div className="flex items-center gap-2">
            <StatusBadge status={job.status} />
            {job.status === 'complete' ? (
              <Button variant="outline" size="sm" disabled={reopening} onClick={onReopen}>
                {reopening ? 'Reopening…' : 'Reopen for review'}
              </Button>
            ) : (
              <Button variant="outline" size="sm" asChild>
                <Link to={`/jobs/${jobId}/review`}>Continue review</Link>
              </Button>
            )}
            <Button size="sm" onClick={onExportCsv} disabled={exporting}>
              {exporting ? 'Exporting…' : 'Export CSV'}
            </Button>
          </div>
        }
      />

      {exportError && <ErrorBanner message={exportError} />}
      {reopenError && <ErrorBanner message={reopenError} />}

      {rows.length === 0 ? (
        <div className="rounded-lg border border-border bg-card">
          <EmptyState title="No audit rows yet" description="No entities have been recorded for this job." />
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Entity</TableHead>
                <TableHead>Class</TableHead>
                <TableHead>Value hash</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Detector</TableHead>
                <TableHead>Conf.</TableHead>
                <TableHead>Timestamp</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.entity_code} className="hover:bg-transparent">
                  <TableCell className="font-mono">{row.entity_code}</TableCell>
                  <TableCell>
                    <CategoryBadge category={row.category} />
                  </TableCell>
                  <TableCell className="font-mono text-xs">{row.value_hash}</TableCell>
                  <TableCell>
                    <ModePill mode={row.action} />
                  </TableCell>
                  <TableCell>{row.detector}</TableCell>
                  <TableCell>{formatPercent(row.confidence)}</TableCell>
                  <TableCell>{formatDateTime(row.created_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
