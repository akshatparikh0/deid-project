import type { Folder, Job, JobStatus } from '../api/types';

interface ActiveJobSnapshot {
  id: number;
  code: string;
  classCount: number;
  entityCount: number;
  status: JobStatus;
}

interface ActiveFolderSnapshot {
  id: number;
  name: string;
}

let activeJob: ActiveJobSnapshot | null = null;
let activeFolder: ActiveFolderSnapshot | null = null;
let queueCount: number | null = null;
/** Set only once the user reaches the end of config rules and chooses to
 * continue — gates the "Upload file" sidebar link so it can't be reached by
 * any route other than document library -> config rules -> continue. */
let uploadReadyFolderId: number | null = null;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((listener) => listener());
}

export function setActiveJob(job: Job | null) {
  activeJob = job
    ? { id: job.id, code: job.code, classCount: job.class_count, entityCount: job.entity_count, status: job.status }
    : null;
  emit();
}

/** The patient folder currently being browsed in the document library —
 * drives the "Config Rules" and "Upload file" sidebar links so they carry
 * that folder forward without requiring the user to re-pick it. */
export function setActiveFolder(folder: Folder | null) {
  activeFolder = folder ? { id: folder.id, name: folder.name } : null;
  uploadReadyFolderId = null;
  emit();
}

export function setUploadReady(folderId: number) {
  uploadReadyFolderId = folderId;
  emit();
}

export function getUploadReadySnapshot() {
  return uploadReadyFolderId;
}

export function setQueueCount(count: number) {
  queueCount = count;
  emit();
}

export function subscribeActiveJob(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getActiveJobSnapshot() {
  return activeJob;
}

export function getActiveFolderSnapshot() {
  return activeFolder;
}

export function getQueueCountSnapshot() {
  return queueCount;
}
