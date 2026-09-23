import type { Folder } from '@/api/types';

export function pathTo(folders: Folder[], id: number | null): Folder[] {
  const path: Folder[] = [];
  let current = id;
  while (current !== null) {
    const folder = folders.find((f) => f.id === current);
    if (!folder) break;
    path.unshift(folder);
    current = folder.parent;
  }
  return path;
}

/** 0 = project, 1 = patient. */
export function folderLevel(folders: Folder[], id: number): number {
  let level = 0;
  let current = folders.find((f) => f.id === id);
  while (current && current.parent !== null) {
    level += 1;
    current = folders.find((f) => f.id === current!.parent);
  }
  return level;
}

export function isPatientFolder(folders: Folder[], id: number): boolean {
  return folderLevel(folders, id) === 1;
}
