import type { Job } from '../api/types';

interface ActiveJobSnapshot {
  id: number;
  code: string;
  classCount: number;
  entityCount: number;
}

let activeJob: ActiveJobSnapshot | null = null;
let queueCount: number | null = null;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((listener) => listener());
}

export function setActiveJob(job: Job | null) {
  activeJob = job
    ? { id: job.id, code: job.code, classCount: job.class_count, entityCount: job.entity_count }
    : null;
  emit();
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

export function getQueueCountSnapshot() {
  return queueCount;
}
