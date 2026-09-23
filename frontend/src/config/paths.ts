/**
 * Single source of truth for client-side route paths. `path` is the pattern
 * registered with the router; `getHref` builds a concrete, type-checked URL
 * for links/redirects so a route is never spelled out as a string literal
 * more than once.
 */
export const paths = {
  login: {
    path: '/login',
    getHref: () => '/login',
  },
  register: {
    path: '/register',
    getHref: () => '/register',
  },
  queue: {
    path: '/queue',
    getHref: (folderId?: number | string | null) =>
      folderId != null ? `/queue?folder=${folderId}` : '/queue',
  },
  upload: {
    path: '/upload',
    getHref: (folderId?: number | string | null) =>
      folderId != null ? `/upload?folder=${folderId}` : '/upload',
  },
  folderRules: {
    path: '/folders/:id/rules',
    getHref: (folderId: number | string) => `/folders/${folderId}/rules`,
  },
  uploadStatus: {
    path: '/uploads/:batchId/status',
    getHref: (batchId: number | string) => `/uploads/${batchId}/status`,
  },
  jobRules: {
    path: '/jobs/:id/rules',
    getHref: (jobId: number | string) => `/jobs/${jobId}/rules`,
  },
  jobReview: {
    path: '/jobs/:id/review',
    getHref: (jobId: number | string) => `/jobs/${jobId}/review`,
  },
  jobAudit: {
    path: '/jobs/:id/audit',
    getHref: (jobId: number | string) => `/jobs/${jobId}/audit`,
  },
} as const;
