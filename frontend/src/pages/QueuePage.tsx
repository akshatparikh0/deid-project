import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ApiError, listJobs } from '../api/client';
import type { Job } from '../api/types';
import { PageHeader } from '../components/Layout';
import { StatusBadge } from '../components/StatusBadge';
import { EmptyState, ErrorBanner, LoadingState } from '../components/States';
import { setQueueCount } from '../lib/activeJob';
import { formatRelative } from '../lib/format';

function routeForJob(job: Job): string | null {
  switch (job.status) {
    case 'complete':
      return `/jobs/${job.id}/audit`;
    case 'failed':
      return null;
    case 'scanning':
      return `/jobs/${job.id}/rules`;
    case 'in_review':
    default:
      return `/jobs/${job.id}/review`;
  }
}

export function QueuePage() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  function load() {
    setLoading(true);
    setError(null);
    listJobs()
      .then((res) => {
        setJobs(res.jobs);
        setQueueCount(res.jobs.length);
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.detail : 'Failed to load document library.');
      })
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  return (
    <div>
      <PageHeader
        title="Document library"
        subtitle="Every document that has entered the pipeline, with its audit record. Sources are purged 24 hours after completion; audit records are retained six years."
        actions={
          <Link to="/upload" className="btn btn-primary">
            Upload document
          </Link>
        }
      />

      {error && <ErrorBanner message={error} onRetry={load} />}

      {loading && !jobs && <LoadingState label="Loading document library…" />}

      {!loading && jobs && jobs.length === 0 && (
        <div className="card">
          <EmptyState
            title="No documents yet"
            description="Upload a PDF to scan it for the 18 HIPAA Safe Harbor identifier classes."
            action={
              <Link to="/upload" className="btn btn-primary">
                Upload your first document
              </Link>
            }
          />
        </div>
      )}

      {jobs && jobs.length > 0 && (
        <div className="card" style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Document</th>
                <th>Job</th>
                <th>Pages</th>
                <th>PHI found</th>
                <th>Status</th>
                <th>Updated</th>
                <th>Audit</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => {
                const dest = routeForJob(job);
                const meta = [job.uploaded_by, job.department].filter(Boolean).join(' · ');
                return (
                  <tr
                    key={job.id}
                    className={dest ? 'clickable' : undefined}
                    onClick={dest ? () => navigate(dest) : undefined}
                  >
                    <td>
                      <div style={{ fontWeight: 500 }}>{job.filename}</div>
                      {meta && (
                        <div className="page-subtitle" style={{ margin: 0, fontSize: 11.5 }}>
                          {meta}
                        </div>
                      )}
                    </td>
                    <td className="mono">{job.code}</td>
                    <td>{job.pages}</td>
                    <td>
                      {job.status === 'failed' ? (
                        <span style={{ color: 'var(--color-danger)' }}>
                          {job.error_message || 'Could not process file'}
                        </span>
                      ) : (
                        <>
                          {job.entity_count} across {job.class_count}{' '}
                          {job.class_count === 1 ? 'class' : 'classes'}
                          {job.unresolved_count > 0 && (
                            <span
                              className="badge"
                              style={{
                                marginLeft: 6,
                                background: 'var(--color-warning-bg)',
                                color: 'var(--color-warning)',
                              }}
                            >
                              {job.unresolved_count} unresolved
                            </span>
                          )}
                        </>
                      )}
                    </td>
                    <td>
                      <StatusBadge status={job.status} />
                    </td>
                    <td>{formatRelative(job.updated_at)}</td>
                    <td>
                      {job.status === 'failed' ? (
                        '—'
                      ) : (
                        <Link
                          to={`/jobs/${job.id}/audit`}
                          onClick={(e) => e.stopPropagation()}
                          className="btn btn-sm btn-ghost"
                        >
                          View
                        </Link>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
