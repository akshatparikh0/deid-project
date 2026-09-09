import type {
  ApiErrorShape,
  ApplyRulesResponse,
  AuditResponse,
  AuthResponse,
  Category,
  EntitiesResponse,
  EntityResponse,
  ExportFormat,
  ExportResponse,
  JobResponse,
  JobsResponse,
  DocumentPayload,
  MeResponse,
  Mode,
  RuleResponse,
  RulesResponse,
} from './types';

const BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000/api';

/** Typed error thrown for any non-2xx API response. */
export class ApiError extends Error {
  status: number;
  detail: string;
  body: ApiErrorShape | undefined;

  constructor(status: number, detail: string, body?: ApiErrorShape) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.body = body;
  }
}

// ---- Auth token storage ----
// Persisted so a page refresh doesn't lose the session. Read once at module
// load; every subsequent change goes through setAuthToken so the in-memory
// value and localStorage never drift apart.

const TOKEN_KEY = 'deid_auth_token';

function readStoredToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

let authToken: string | null = readStoredToken();

export function getAuthToken(): string | null {
  return authToken;
}

export function setAuthToken(token: string | null): void {
  authToken = token;
  try {
    if (token) {
      localStorage.setItem(TOKEN_KEY, token);
    } else {
      localStorage.removeItem(TOKEN_KEY);
    }
  } catch {
    // localStorage unavailable (private mode, etc.) — session just won't survive a refresh.
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (authToken) headers.set('Authorization', `Token ${authToken}`);

  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, 'Could not reach the server. Check your connection and try again.');
  }

  if (!res.ok) {
    let body: ApiErrorShape | undefined;
    try {
      body = (await res.json()) as ApiErrorShape;
    } catch {
      // response had no / invalid JSON body
    }
    const detail = body?.detail ?? `Request failed with status ${res.status}`;
    if (res.status === 401 && path !== '/auth/login/') {
      setAuthToken(null);
      window.dispatchEvent(new CustomEvent('auth:unauthorized'));
    }
    throw new ApiError(res.status, detail, body);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return (await res.json()) as T;
}

function json(body: unknown): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
}

// ---- Jobs ----

export interface CreateJobParams {
  file: File;
  uploaded_by?: string;
  department?: string;
  preset?: Mode;
}

export function createJob(params: CreateJobParams): Promise<JobResponse> {
  const form = new FormData();
  form.append('file', params.file);
  if (params.uploaded_by) form.append('uploaded_by', params.uploaded_by);
  if (params.department) form.append('department', params.department);
  if (params.preset) form.append('preset', params.preset);
  return request<JobResponse>('/jobs/', { method: 'POST', body: form });
}

export function listJobs(): Promise<JobsResponse> {
  return request<JobsResponse>('/jobs/');
}

export function getJob(id: number): Promise<JobResponse> {
  return request<JobResponse>(`/jobs/${id}/`);
}

export function getDocument(id: number): Promise<DocumentPayload> {
  return request<DocumentPayload>(`/jobs/${id}/document/`);
}

// ---- Entities ----

export function updateEntity(id: number, mode: Mode): Promise<EntityResponse> {
  return request<EntityResponse>(`/entities/${id}/`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode }),
  });
}

export function bulkUpdateEntities(
  jobId: number,
  params: { mode: Mode; category?: Category },
): Promise<EntitiesResponse> {
  return request<EntitiesResponse>(`/jobs/${jobId}/entities/bulk_update/`, json(params));
}

// ---- Rules ----

export function getRules(jobId: number): Promise<RulesResponse> {
  return request<RulesResponse>(`/jobs/${jobId}/rules/`);
}

export function updateRule(
  jobId: number,
  category: Category,
  patch: Partial<{ enabled: boolean; mode: Mode; token: string }>,
): Promise<RuleResponse> {
  return request<RuleResponse>(`/jobs/${jobId}/rules/${category}/`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
}

export function applyRules(jobId: number): Promise<ApplyRulesResponse> {
  return request<ApplyRulesResponse>(`/jobs/${jobId}/rules/apply/`, { method: 'POST' });
}

// ---- Lifecycle ----

export function completeJob(jobId: number, force?: boolean): Promise<JobResponse> {
  return request<JobResponse>(`/jobs/${jobId}/complete/`, json({ force: !!force }));
}

export function reopenJob(jobId: number): Promise<JobResponse> {
  return request<JobResponse>(`/jobs/${jobId}/reopen/`, { method: 'POST' });
}

// ---- Audit ----

export function getAudit(jobId: number): Promise<AuditResponse> {
  return request<AuditResponse>(`/jobs/${jobId}/audit/`);
}

// ---- Export ----

export function exportJob(jobId: number, formats: ExportFormat[]): Promise<ExportResponse> {
  return request<ExportResponse>(`/jobs/${jobId}/export/`, json({ formats }));
}

// ---- Auth ----

export function register(params: { name: string; username: string; password: string }): Promise<AuthResponse> {
  return request<AuthResponse>('/auth/register/', json(params));
}

export function login(params: { username: string; password: string }): Promise<AuthResponse> {
  return request<AuthResponse>('/auth/login/', json(params));
}

export function logout(): Promise<void> {
  return request<void>('/auth/logout/', { method: 'POST' });
}

export function getMe(): Promise<MeResponse> {
  return request<MeResponse>('/auth/me/');
}

/** Resolve a (possibly relative) file URL returned by the API against the API origin. */
export function resolveApiUrl(url: string): string {
  if (/^https?:\/\//i.test(url)) return url;
  // BASE_URL already ends in "/api"; download urls from the contract start with "/api/..."
  const origin = BASE_URL.replace(/\/api\/?$/, '');
  return `${origin}${url}`;
}

export { BASE_URL };
