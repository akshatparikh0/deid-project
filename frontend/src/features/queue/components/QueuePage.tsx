import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Folder as FolderIcon } from 'lucide-react';
import {
  ApiError,
  createFolder,
  deleteFolder,
  deleteJob,
  listFolders,
  listJobs,
  updateFolder,
  updateJob,
} from '@/api/client';
import type { Folder, Job } from '@/api/types';
import { ConfirmModal } from '@/components/ConfirmModal';
import { PageHeader } from '@/components/Layout';
import { StatusBadge } from '@/components/StatusBadge';
import { EmptyState, ErrorBanner, LoadingState } from '@/components/States';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { cn } from '@/lib/utils';
import { folderLevel, pathTo } from '@/lib/folders';
import { formatRelative } from '@/lib/format';
import { routeForJobStatus } from '@/lib/jobRoute';
import { showToast } from '@/lib/toast';
import { setActiveFolder, setQueueCount } from '@/stores/activeJob';
import { NamePromptModal } from './NamePromptModal';

function routeForJob(job: Job): string | null {
  return routeForJobStatus(job.id, job.status, job.batch);
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
            ? 'Sources are purged 24 hours after completion; audit records are retained six years.'
            : 'Every project, organized by patient, with its documents and audit record. Sources are purged 24 hours after completion; audit records are retained six years.'
        }
        actions={
          <>
            {canCreateFolder && (
              <Button variant="outline" onClick={() => setModal({ kind: 'newFolder' })}>
                New {kindLabel}
              </Button>
            )}
            {canConfigureRules && (
              <Button asChild>
                <Link to={rulesHref}>Add document</Link>
              </Button>
            )}
          </>
        }
      />

      <div className="mb-3.5 flex flex-wrap items-center gap-0.5 text-[13px]">
        <button
          type="button"
          className="rounded px-1 py-0.5 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          onClick={() => openFolder(null)}
        >
          Projects
        </button>
        {trail.map((folder, i) => (
          <span key={folder.id} className="flex items-center gap-0.5">
            <span className="mx-0.5 text-muted-foreground/50" aria-hidden="true">
              /
            </span>
            {i === trail.length - 1 ? (
              <span className="rounded px-1 py-0.5 font-semibold text-foreground">{folder.name}</span>
            ) : (
              <button
                type="button"
                className="rounded px-1 py-0.5 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                onClick={() => openFolder(folder.id)}
              >
                {folder.name}
              </button>
            )}
          </span>
        ))}
      </div>

      {error && <ErrorBanner message={error} onRetry={load} />}

      {loading && !folders && <LoadingState label="Loading document library…" />}

      {!loading && folders && children.length === 0 && jobs && jobs.length === 0 && (
        <div className="rounded-lg border border-border bg-card">
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
                <Button asChild>
                  <Link to={rulesHref}>Add document</Link>
                </Button>
              ) : (
                <Button onClick={() => setModal({ kind: 'newFolder' })}>New {kindLabel}</Button>
              )
            }
          />
        </div>
      )}

      {children.length > 0 && (
        <div
          className={cn(
            'overflow-x-auto rounded-lg border border-border bg-card',
            jobs && jobs.length > 0 ? 'mb-4' : undefined,
          )}
        >
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Name</TableHead>
                <TableHead>Contains</TableHead>
                <TableHead>Updated</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {children.map((folder) => (
                <TableRow key={folder.id} className="cursor-pointer" onClick={() => openFolder(folder.id)}>
                  <TableCell className="whitespace-normal">
                    <div className="flex items-center gap-2 font-medium">
                      <FolderIcon className="size-3.5 shrink-0 text-status-warning" aria-hidden="true" />
                      {folder.name}
                    </div>
                  </TableCell>
                  <TableCell className="whitespace-normal text-muted-foreground">
                    {folder.subfolder_count > 0 &&
                      `${folder.subfolder_count} ${folder.subfolder_count === 1 ? 'folder' : 'folders'}`}
                    {folder.subfolder_count > 0 && folder.document_count > 0 && ', '}
                    {folder.document_count > 0 &&
                      `${folder.document_count} ${folder.document_count === 1 ? 'document' : 'documents'}`}
                    {folder.subfolder_count === 0 && folder.document_count === 0 && 'Empty'}
                  </TableCell>
                  <TableCell>{formatRelative(folder.updated_at)}</TableCell>
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <div className="flex justify-end gap-1.5">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => setModal({ kind: 'renameFolder', folder })}
                      >
                        Rename
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                        onClick={() => setConfirm({ kind: 'deleteFolder', folder })}
                      >
                        Delete
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {jobs && jobs.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Document</TableHead>
                <TableHead>Job</TableHead>
                <TableHead>Pages</TableHead>
                <TableHead>PHI found</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Updated</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {jobs.map((job) => {
                const dest = routeForJob(job);
                const meta = [job.uploaded_by, job.department].filter(Boolean).join(' · ');
                return (
                  <TableRow
                    key={job.id}
                    className={dest ? 'cursor-pointer' : undefined}
                    onClick={dest ? () => navigate(dest, { state: { from: 'queue' } }) : undefined}
                  >
                    <TableCell className="whitespace-normal">
                      <div className="font-medium">{job.filename}</div>
                      {meta && <div className="mt-0.5 text-[11.5px] text-muted-foreground">{meta}</div>}
                    </TableCell>
                    <TableCell className="font-mono">{job.code}</TableCell>
                    <TableCell>{job.pages}</TableCell>
                    <TableCell className="whitespace-normal">
                      {job.status === 'failed' ? (
                        <span className="text-destructive">{job.error_message || 'Could not process file'}</span>
                      ) : (
                        <>
                          {job.entity_count} across {job.class_count}{' '}
                          {job.class_count === 1 ? 'class' : 'classes'}
                          {job.unresolved_count > 0 && (
                            <Badge
                              variant="outline"
                              className="ml-1.5 border-transparent bg-status-warning-bg text-status-warning"
                            >
                              {job.unresolved_count} unresolved
                            </Badge>
                          )}
                        </>
                      )}
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={job.status} />
                    </TableCell>
                    <TableCell>{formatRelative(job.updated_at)}</TableCell>
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <div className="flex flex-wrap justify-end gap-1.5">
                        {job.status !== 'failed' && (
                          <Button asChild variant="ghost" size="sm">
                            <Link to={`/jobs/${job.id}/audit`}>View</Link>
                          </Button>
                        )}
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => setModal({ kind: 'renameJob', job })}
                        >
                          Rename
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                          onClick={() => setConfirm({ kind: 'deleteJob', job })}
                        >
                          Delete
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
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
