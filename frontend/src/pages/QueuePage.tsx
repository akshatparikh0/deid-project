import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  ApiError,
  createFolder,
  deleteFolder,
  deleteJob,
  listFolders,
  listJobs,
  updateFolder,
  updateJob,
} from '../api/client';
import type { Folder, Job } from '../api/types';
import { ConfirmModal } from '../components/ConfirmModal';
import { PageHeader } from '../components/Layout';
import { NamePromptModal } from '../components/NamePromptModal';
import { StatusBadge } from '../components/StatusBadge';
import { EmptyState, ErrorBanner, LoadingState } from '../components/States';
import { setActiveFolder, setQueueCount } from '../lib/activeJob';
import { folderLevel, pathTo } from '../lib/folders';
import { formatRelative } from '../lib/format';
import { routeForJobStatus } from '../lib/jobRoute';
import { showToast } from '../lib/toast';

function routeForJob(job: Job): string | null {
  return routeForJobStatus(job.id, job.status, job.batch, job.entity_count);
}

/** By convention the top level holds projects and the next level holds
 * patients — purely a naming convention for the "New …" button and empty
 * states. Nesting itself is unrestricted; anything deeper is just a folder. */
function newChildKind(folders: Folder[], parentId: number | null): 'project' | 'patient' | 'folder' {
  const newLevel = parentId === null ? 0 : folderLevel(folders, parentId) + 1;
  if (newLevel === 0) return 'project';
  if (newLevel === 1) return 'patient';
  return 'folder';
}

type Modal =
  | { kind: 'newFolder' }
  | { kind: 'renameFolder'; folder: Folder }
  | { kind: 'renameJob'; job: Job };

type Confirm =
  | { kind: 'deleteFolder'; folder: Folder }
  | { kind: 'deleteJob'; job: Job };

export function QueuePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const folderParam = searchParams.get('folder');
  const currentId = folderParam ? Number(folderParam) : null;

  const [folders, setFolders] = useState<Folder[] | null>(null);
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modal, setModal] = useState<Modal | null>(null);
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const navigate = useNavigate();
  const requestIdRef = useRef(0);

  function refreshBadge() {
    listJobs()
      .then((res) => setQueueCount(res.jobs.length))
      .catch(() => {});
  }

  function load() {
    const requestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);
    Promise.all([listFolders(), listJobs({ folder: currentId })])
      .then(([folderRes, jobRes]) => {
        if (requestIdRef.current !== requestId) return; // a newer navigation superseded this fetch
        setFolders(folderRes.folders);
        setJobs(jobRes.jobs);
      })
      .catch((err: unknown) => {
        if (requestIdRef.current !== requestId) return;
        setError(err instanceof ApiError ? err.detail : 'Failed to load document library.');
      })
      .finally(() => {
        if (requestIdRef.current === requestId) setLoading(false);
      });
  }

  useEffect(load, [currentId]);
  useEffect(refreshBadge, []);
  useEffect(() => {
    if (!folders || currentId === null) return;
    const folder = folders.find((f) => f.id === currentId);
    if (folder && folderLevel(folders, currentId) === 1) setActiveFolder(folder);
  }, [folders, currentId]);

  function openFolder(id: number | null) {
    if (id === null) setSearchParams({});
    else setSearchParams({ folder: String(id) });
  }

  const trail = folders ? pathTo(folders, currentId) : [];
  const children = folders ? folders.filter((f) => f.parent === currentId) : [];
  const currentLevel = folders && currentId !== null ? folderLevel(folders, currentId) : -1;
  const isPatientFolder = currentLevel === 1;
  const kind = folders ? newChildKind(folders, currentId) : 'folder';
  const kindLabel = kind === 'project' ? 'project' : kind === 'patient' ? 'patient' : 'folder';
  // The tree is exactly project -> patient -> documents: no new folders inside a
  // patient folder, and documents can only be uploaded inside one.
  const canCreateFolder = !isPatientFolder;
  const canConfigureRules = isPatientFolder;
  const rulesHref = currentId ? `/folders/${currentId}/rules` : '/queue';

  async function onCreateFolder(name: string) {
    await createFolder({ name, parent: currentId });
    showToast(`${kindLabel[0].toUpperCase()}${kindLabel.slice(1)} "${name}" created.`);
    load();
  }

  async function onRenameFolder(folder: Folder, name: string) {
    await updateFolder(folder.id, { name });
    showToast(`Renamed to "${name}".`);
    load();
  }

  async function onRenameJob(job: Job, filename: string) {
    await updateJob(job.id, { filename });
    showToast(`Renamed to "${filename}".`);
    load();
  }

  async function onDeleteFolder(folder: Folder) {
    const recursive = folder.subfolder_count > 0 || folder.document_count > 0;
    await deleteFolder(folder.id, recursive);
    showToast(`Deleted "${folder.name}".`);
    refreshBadge();
    load();
  }

  async function onDeleteJob(job: Job) {
    await deleteJob(job.id);
    showToast(`Deleted "${job.filename}".`);
    refreshBadge();
    load();
  }

  return (
    <div>
      <PageHeader
        title={trail.length ? trail[trail.length - 1].name : 'Document library'}
        subtitle={
          trail.length
            ? 'Sources are purged immediately on completion; audit records are retained six years.'
            : 'Every project, organized by patient, with its documents and audit record. Sources are purged immediately on completion; audit records are retained six years.'
        }
        actions={
          <>
            {canCreateFolder && (
              <button className="btn" onClick={() => setModal({ kind: 'newFolder' })}>
                New {kindLabel}
              </button>
            )}
            {canConfigureRules && (
              <Link to={rulesHref} className="btn btn-primary">
                Add document
              </Link>
            )}
          </>
        }
      />

      <div className="breadcrumbs" style={{ marginBottom: 14 }}>
        <button type="button" className="breadcrumb-item" onClick={() => openFolder(null)}>
          Projects
        </button>
        {trail.map((folder, i) => (
          <span key={folder.id}>
            <span className="breadcrumb-sep" aria-hidden="true">
              /
            </span>
            {i === trail.length - 1 ? (
              <span className="breadcrumb-item breadcrumb-current">{folder.name}</span>
            ) : (
              <button type="button" className="breadcrumb-item" onClick={() => openFolder(folder.id)}>
                {folder.name}
              </button>
            )}
          </span>
        ))}
      </div>

      {error && <ErrorBanner message={error} onRetry={load} />}

      {loading && !folders && <LoadingState label="Loading document library…" />}

      {!loading && folders && children.length === 0 && jobs && jobs.length === 0 && (
        <div className="card">
          <EmptyState
            title={isPatientFolder ? 'No documents yet' : `No ${trail.length ? 'patients' : 'projects'} yet`}
            description={
              isPatientFolder
                ? 'Configure the detection ruleset, then add a document to get started.'
                : trail.length
                  ? 'Create a patient folder to start uploading documents.'
                  : 'Create a project to start organizing documents by patient.'
            }
            action={
              canConfigureRules ? (
                <Link to={rulesHref} className="btn btn-primary">
                  Add document
                </Link>
              ) : (
                <button className="btn btn-primary" onClick={() => setModal({ kind: 'newFolder' })}>
                  New {kindLabel}
                </button>
              )
            }
          />
        </div>
      )}

      {children.length > 0 && (
        <div className="card" style={{ overflowX: 'auto', marginBottom: jobs && jobs.length > 0 ? 16 : 0 }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Contains</th>
                <th>Updated</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {children.map((folder) => (
                <tr key={folder.id} className="clickable" onClick={() => openFolder(folder.id)}>
                  <td>
                    <span className="folder-icon" aria-hidden="true" />
                    <span style={{ fontWeight: 500 }}>{folder.name}</span>
                  </td>
                  <td className="page-subtitle" style={{ margin: 0 }}>
                    {folder.subfolder_count > 0 &&
                      `${folder.subfolder_count} ${folder.subfolder_count === 1 ? 'folder' : 'folders'}`}
                    {folder.subfolder_count > 0 && folder.document_count > 0 && ', '}
                    {folder.document_count > 0 &&
                      `${folder.document_count} ${folder.document_count === 1 ? 'document' : 'documents'}`}
                    {folder.subfolder_count === 0 && folder.document_count === 0 && 'Empty'}
                  </td>
                  <td>{formatRelative(folder.updated_at)}</td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                      <button
                        type="button"
                        className="btn btn-sm btn-ghost"
                        onClick={() => setModal({ kind: 'renameFolder', folder })}
                      >
                        Rename
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-ghost"
                        style={{ color: 'var(--color-danger)' }}
                        onClick={() => setConfirm({ kind: 'deleteFolder', folder })}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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
                <th></th>
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
                    onClick={dest ? () => navigate(dest, { state: { from: 'queue' } }) : undefined}
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
                    <td onClick={(e) => e.stopPropagation()}>
                      <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                        {job.status !== 'failed' && (
                          <Link to={`/jobs/${job.id}/audit`} className="btn btn-sm btn-ghost">
                            View
                          </Link>
                        )}
                        <button
                          type="button"
                          className="btn btn-sm btn-ghost"
                          onClick={() => setModal({ kind: 'renameJob', job })}
                        >
                          Rename
                        </button>
                        <button
                          type="button"
                          className="btn btn-sm btn-ghost"
                          style={{ color: 'var(--color-danger)' }}
                          onClick={() => setConfirm({ kind: 'deleteJob', job })}
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {modal?.kind === 'newFolder' && (
        <NamePromptModal
          title={`New ${kindLabel}`}
          label={`${kindLabel[0].toUpperCase()}${kindLabel.slice(1)} name`}
          confirmLabel="Create"
          onSubmit={onCreateFolder}
          onClose={() => setModal(null)}
        />
      )}
      {modal?.kind === 'renameFolder' && (
        <NamePromptModal
          title="Rename"
          label="Name"
          initialValue={modal.folder.name}
          confirmLabel="Rename"
          onSubmit={(name) => onRenameFolder(modal.folder, name)}
          onClose={() => setModal(null)}
        />
      )}
      {modal?.kind === 'renameJob' && (
        <NamePromptModal
          title="Rename document"
          label="Filename"
          initialValue={modal.job.filename}
          confirmLabel="Rename"
          onSubmit={(name) => onRenameJob(modal.job, name)}
          onClose={() => setModal(null)}
        />
      )}

      {confirm?.kind === 'deleteFolder' && (
        <ConfirmModal
          title={`Delete "${confirm.folder.name}"?`}
          message={
            confirm.folder.subfolder_count > 0 || confirm.folder.document_count > 0
              ? `This folder contains ${confirm.folder.subfolder_count} subfolder${confirm.folder.subfolder_count === 1 ? '' : 's'} and ${confirm.folder.document_count} document${confirm.folder.document_count === 1 ? '' : 's'}. Deleting it permanently deletes everything inside. This cannot be undone.`
              : 'This cannot be undone.'
          }
          onConfirm={() => onDeleteFolder(confirm.folder)}
          onClose={() => setConfirm(null)}
        />
      )}
      {confirm?.kind === 'deleteJob' && (
        <ConfirmModal
          title={`Delete "${confirm.job.filename}"?`}
          message="This permanently deletes the document and its audit record. This cannot be undone."
          onConfirm={() => onDeleteJob(confirm.job)}
          onClose={() => setConfirm(null)}
        />
      )}
    </div>
  );
}
