// Types mirroring the backend API contract exactly.
// See API_CONTRACT.md (shared out-of-band with the backend team) for the source of truth.

export type Category =
  | 'patient_name'
  | 'physician_name'
  | 'name'
  | 'facility'
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

export interface Folder {
  id: number;
  name: string;
  parent: number | null;
  subfolder_count: number;
  document_count: number;
  created_at: string;
  updated_at: string;
}

export interface Job {
  id: number;
  code: string; // "JOB-0001"
  filename: string;
  uploaded_by: string;
  department: string;
  folder: number | null;
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

export interface EntityBox {
  x0: number;
  top: number;
  x1: number;
  bottom: number;
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
  detector: string; // "pattern" | "heuristic" | "context"
  block_index: number; // index into DocumentPayload.blocks
  boxes: EntityBox[]; // page-coordinate (PDF points) bounding boxes, one per visual line touched
}

export interface DocumentPage {
  number: number; // 1-indexed
  width: number; // PDF points — same coordinate space as Entity.boxes
  height: number;
  image_url: string; // relative; resolve with resolveApiUrl and fetch with auth (see fetchAuthenticatedBlob)
}

export type BlockPart = { text: string } | { entity: string }; // entity `code`

export interface DocumentBlock {
  index: number;
  page: number;
  type: 'title' | 'sub' | 'h' | 'p' | 'table_row';
  source: 'text' | 'ocr'; // 'ocr' = Tesseract fallback for a page with no native text layer
  parts: BlockPart[];
}

export interface DocumentPayload {
  pages: DocumentPage[];
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

/** A patient folder's default ruleset, configured before any document is
 * uploaded into it — no "found" counts yet since nothing has been scanned. */
export interface FolderCategoryRule {
  category: Category;
  enabled: boolean;
  mode: Mode;
  token: string;
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

export interface FolderResponse {
  folder: Folder;
}

export interface FoldersResponse {
  folders: Folder[];
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

export interface FolderRulesResponse {
  rules: FolderCategoryRule[];
}

export interface FolderRuleResponse {
  rule: FolderCategoryRule;
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

// ---- Auth ----

export interface AuthUser {
  id: number;
  username: string;
  name: string;
}

export interface AuthResponse {
  user: AuthUser;
  token: string;
}

export interface MeResponse {
  user: AuthUser;
}
