# PHI De-Identification — API Contract

Backend: Django + Django REST Framework, running at `http://localhost:8000`.
All endpoints are prefixed `/api`. JSON in/out except upload (multipart) and file downloads.
CORS is open for `http://localhost:5173` (Vite dev server).

## Enums

```ts
type Category =
  | 'name' | 'geo' | 'date' | 'phone' | 'fax' | 'email' | 'ssn' | 'mrn'
  | 'plan' | 'account' | 'license' | 'vehicle' | 'device' | 'url' | 'ip'
  | 'biometric' | 'photo' | 'other';

type Mode = 'redact' | 'mask' | 'pseudo' | 'keep';

type JobStatus = 'scanning' | 'in_review' | 'complete' | 'failed';
```

Category metadata (label + accent color hex) the frontend should hardcode, keyed by the
`category` string returned by the API — the backend does NOT send label/color inline on
every entity, only on the `/rules/` endpoint (see below):

```
name      Name                  #7C4DBC
geo       Geographic            #2D6FB8
date      Date                  #B8792D
phone     Telephone             #1F8A70
fax       Fax                   #1F8A70
email     Email                 #1F8A70
ssn       SSN                   #A4291F
mrn       Medical record no.    #A4291F
plan      Health plan no.       #A4291F
account   Account no.           #8A5A1B
license   Certificate / licence #8A5A1B
vehicle   Vehicle identifier    #5B6770
device    Device identifier     #5B6770
url       URL                   #2D6FB8
ip        IP address            #2D6FB8
biometric Biometric             #7C4DBC
photo     Full-face image       #7C4DBC
other     Other identifier      #5B6770
```

Mode labels: redact="Redact", mask="Mask", pseudo="Pseudonymize", keep="Keep".

## Types

```ts
interface Job {
  id: number;
  code: string;                 // "JOB-0001"
  filename: string;
  uploaded_by: string;
  department: string;
  pages: number;
  status: JobStatus;
  error_message: string | null;
  entity_count: number;
  unresolved_count: number;     // entities currently mode === 'keep'
  class_count: number;          // distinct categories detected
  confidence_threshold: number; // 0..1
  created_at: string;           // ISO datetime
  updated_at: string;
}

interface Entity {
  id: number;
  code: string;          // "E-01" (stable per job, ordered by first appearance)
  category: Category;
  value: string;         // original plaintext span
  surrogate_value: string; // deterministic fake replacement for 'pseudo' mode
  mode: Mode;
  confidence: number;    // 0..1
  page: number;          // 1-indexed
  detector: string;      // "pattern" | "heuristic"
  block_index: number;   // index into DocumentPayload.blocks
}

type BlockPart =
  | { text: string }
  | { entity: string };  // entity `code`

interface DocumentBlock {
  index: number;
  page: number;
  type: 'title' | 'sub' | 'h' | 'p';
  parts: BlockPart[];
}

interface DocumentPayload {
  blocks: DocumentBlock[];
  entities: Entity[];
}

interface CategoryRule {
  category: Category;
  found: number;      // count of entities of this category in the job (0 if none)
  enabled: boolean;
  mode: Mode;          // default mode applied to this category on "apply rules"
  token: string;       // e.g. "[NAME]" — used when mode === 'mask'
}

interface AuditRow {
  entity_code: string;
  category: Category;
  value_hash: string;   // "sha256:xxxxxxxx" — never the plaintext value
  action: Mode;
  detector: string;
  confidence: number;
  created_at: string;
}

interface ExportFile {
  format: 'pdf' | 'csv' | 'json';
  filename: string;
  url: string;          // absolute path, e.g. "/api/jobs/7/export/download/pdf/"
}
```

## Endpoints

### `POST /api/jobs/`
multipart/form-data: `file` (PDF, required), `uploaded_by` (string, optional),
`department` (string, optional), `preset` (Mode, optional, default `"mask"` — used as the
initial default mode for every detected category's rule).

Synchronously: saves the upload, extracts text per page, runs PHI detection, creates
Entity rows (all starting at `mode = preset`) and CategoryRule rows (`enabled=true`,
`mode=preset`, `token` = default token for that category), sets `status="in_review"`.
If the PDF can't be parsed (encrypted, no extractable text, corrupt), creates the Job
with `status="failed"` and a human-readable `error_message`, still returns 201.

Returns `201 { job: Job }`.

### `GET /api/jobs/`
Returns `200 { jobs: Job[] }`, newest first.

### `GET /api/jobs/:id/`
Returns `200 { job: Job }`. `404 { detail }` if missing.

### `GET /api/jobs/:id/document/`
Returns `200 DocumentPayload`.

### `PATCH /api/entities/:id/`
Body: `{ mode: Mode }`. Returns `200 { entity: Entity }`.

### `POST /api/jobs/:id/entities/bulk_update/`
Body: `{ mode: Mode, category?: Category }` (omit category to apply to every entity in
the job). Returns `200 { entities: Entity[] }` (the full updated list for the job).

### `GET /api/jobs/:id/rules/`
Returns `200 { rules: CategoryRule[] }` — one row per one of the 18 canonical categories
(not just ones found), ordered as in the table above.

### `PATCH /api/jobs/:id/rules/:category/`
Body: any of `{ enabled?, mode?, token? }`. Returns `200 { rule: CategoryRule }`.

### `POST /api/jobs/:id/rules/apply/`
Applies every enabled rule's `mode` to all entities of that rule's category (categories
with `enabled=false` are left untouched — their entities keep whatever mode they have).
Returns `200 { job: Job, entities: Entity[] }`.

### `POST /api/jobs/:id/complete/`
Body: `{ force?: boolean }`. If any entity has `mode === 'keep'` and `force` is not
`true`, returns `409 { detail, unresolved_count }`. Otherwise sets `status="complete"`
and returns `200 { job: Job }`.

### `POST /api/jobs/:id/reopen/`
Sets `status="in_review"`. Returns `200 { job: Job }`.

### `GET /api/jobs/:id/audit/`
Returns `200 { rows: AuditRow[] }`, one per entity, ordered by entity `code`.

### `POST /api/jobs/:id/export/`
Body: `{ formats: Array<'pdf'|'csv'|'json'> }`. Generates the requested artifacts server
side (a reconstructed de-identified PDF via reportlab, the audit CSV, an entity-manifest
JSON) and returns `200 { files: ExportFile[] }`.

### `GET /api/jobs/:id/export/download/:format/`
Streams the generated file (`application/pdf`, `text/csv`, or `application/json`) with a
`Content-Disposition: attachment` header. `404` if it hasn't been generated yet (call
`/export/` first).

## Error shape
All non-2xx responses are `{ "detail": string, ...extra }`.

## Notes for the frontend build
- Base URL: read from `import.meta.env.VITE_API_BASE_URL`, default `"http://localhost:8000/api"`.
- Vite dev server on port 5173 (Django CORS already allows it — no proxy needed, just fetch absolute URLs).
- Build the whole thing for real: routed screens (react-router-dom), a typed api client,
  and components for Queue (document library), Upload, Rules (detection settings),
  Review (side-by-side original/de-identified panes + entity inspector), Audit, and an
  Export modal — this mirrors a Safe-Harbor PHI redaction tool's real workflow.
- Visual language: dark left nav rail (~216px, bg #0E1216, text #8C959E, active item
  lighter bg #1B2229 + off-white text), warm cream content background (#FAF9F6), cards on
  white with hairline borders (#E4E1D9), IBM Plex Sans for UI text and IBM Plex Serif for
  document titles / IBM Plex Mono for codes, hashes, tokens — load all three from Google
  Fonts in `index.html`. Category color dots/badges use the hex table above. Redacted
  spans render as solid black blocks with transparent text; masked spans render as small
  mono pills; pseudonymized spans render as dashed-underline blue text; kept spans render
  as dotted-underline amber text — mirror this for both the entity list's mode pill and
  the document pane's inline span styling.
- Handle loading/error states, and disable "Mark complete" while `unresolved_count > 0`
  unless the user explicitly confirms (send `force: true`).
- Write a root `README.md` in `frontend/` with setup + run instructions (`npm install`,
  `npm run dev`).
- After scaffolding, run `npm run build` yourself and fix any TypeScript errors before
  finishing — the build must succeed cleanly.
