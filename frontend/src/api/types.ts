// Types mirroring the backend API contract exactly.
// See API_CONTRACT.md (shared out-of-band with the backend team) for the source of truth.

export type Category =
  | 'name'
  | 'geo'
  | 'date'
  | 'phone'
  | 'fax'
  | 'email'
  | 'ssn'
  | 'mrn'
  | 'plan'
  | 'account'
  | 'license'
  | 'vehicle'
  | 'device'
  | 'url'
  | 'ip'
  | 'biometric'
  | 'photo'
  | 'other';

export type Mode = 'redact' | 'mask' | 'pseudo' | 'keep';

export type JobStatus = 'scanning' | 'in_review' | 'complete' | 'failed';

export interface Job {
  id: number;
  code: string; // "JOB-0001"
  filename: string;
  uploaded_by: string;
  department: string;
  pages: number;
  status: JobStatus;
  error_message: string | null;
  entity_count: number;
  unresolved_count: number; // entities currently mode === 'keep'
  class_count: number; // distinct categories detected
  confidence_threshold: number; // 0..1
  created_at: string; // ISO datetime
  updated_at: string;
}

export interface Entity {
  id: number;
  code: string; // "E-01" (stable per job, ordered by first appearance)
  category: Category;
  value: string; // original plaintext span
  surrogate_value: string; // deterministic fake replacement for 'pseudo' mode
  mode: Mode;
  confidence: number; // 0..1
  page: number; // 1-indexed
  detector: string; // "pattern" | "heuristic"
  block_index: number; // index into DocumentPayload.blocks
}

export type BlockPart = { text: string } | { entity: string }; // entity `code`

export interface DocumentBlock {
  index: number;
  page: number;
  type: 'title' | 'sub' | 'h' | 'p';
  parts: BlockPart[];
}

export interface DocumentPayload {
  blocks: DocumentBlock[];
  entities: Entity[];
}

export interface CategoryRule {
  category: Category;
  found: number; // count of entities of this category in the job (0 if none)
  enabled: boolean;
  mode: Mode; // default mode applied to this category on "apply rules"
  token: string; // e.g. "[NAME]" — used when mode === 'mask'
}

export interface AuditRow {
  entity_code: string;
  category: Category;
  value_hash: string; // "sha256:xxxxxxxx" — never the plaintext value
  action: Mode;
  detector: string;
  confidence: number;
  created_at: string;
}

export type ExportFormat = 'pdf' | 'csv' | 'json';

export interface ExportFile {
  format: ExportFormat;
  filename: string;
  url: string; // absolute path, e.g. "/api/jobs/7/export/download/pdf/"
}

// ---- Response envelopes ----

export interface JobResponse {
  job: Job;
}

export interface JobsResponse {
  jobs: Job[];
}

export interface EntityResponse {
  entity: Entity;
}

export interface EntitiesResponse {
  entities: Entity[];
}

export interface RulesResponse {
  rules: CategoryRule[];
}

export interface RuleResponse {
  rule: CategoryRule;
}

export interface ApplyRulesResponse {
  job: Job;
  entities: Entity[];
}

export interface AuditResponse {
  rows: AuditRow[];
}

export interface ExportResponse {
  files: ExportFile[];
}

export interface ApiErrorShape {
  detail: string;
  [key: string]: unknown;
}
