# PHI De-Identification — API Contract

Backend: Django + Django REST Framework, running at `http://localhost:8000`.
All endpoints are prefixed `/api`. JSON in/out except upload (multipart) and file downloads.
CORS is open for `http://localhost:5173` (Vite dev server).

## Enums

```ts
type Category =
  | 'patient_name' | 'physician_name' | 'person_name' | 'guarantor_name'
  | 'facility_name' | 'employer' | 'date_of_birth' | 'date_of_service'
  | 'other_date' | 'age_over_89' | 'age_89_or_below' | 'street_address'
  | 'zip_code' | 'phone' | 'fax' | 'email' | 'url' | 'ssn' | 'mrn'
  | 'member_id' | 'account' | 'payment_card' | 'ip_address' | 'device_id'
  | 'license' | 'vehicle' | 'biometric' | 'photo' | 'other';

type Mode = 'redact' | 'mask' | 'pseudo' | 'keep';

// "queued": uploaded, not yet picked up by a worker (async processing —
// the backend runs this synchronously in-process when no Celery broker is
// configured, so this state is normally instantaneous in dev).
// "finalizing": completion requested — running true-PDF-redaction plus
// second-pass verification; also normally instantaneous, but a real,
// pollable state.
type JobStatus = 'queued' | 'scanning' | 'in_review' | 'finalizing' | 'complete' | 'failed';
```

This is the unified entity taxonomy shared by the Django app and the
project configuration schema (`config/default_policy.json`) —
`patient_name` / `physician_name` /
`guarantor_name` / `person_name` are split out as their own categories even
though Safe Harbor's "Names" identifier covers all four the same way; the
split is purely for reviewer clarity, and `guarantor_name` also matches its
own named requirement (guarantor/next-of-kin). `facility_name` and
`employer` aren't themselves numbered Safe Harbor identifiers, but are
tracked the same way since they're routinely identifying. Dates are split
into `date_of_birth` / `date_of_service` / `other_date` so the per-category
policy can leave the date of service unchanged (it orders a patient's
record) while masking every other date — Safe Harbor's date identifier
covers all of them the same way. `payment_card` is its own category (no
longer folded into `other`).

Category metadata (label + accent color hex) the frontend hardcodes (see
`frontend/src/lib/categories.ts`), keyed by the `category` string returned
by the API — the backend does NOT send label/color inline on every entity,
only on the `/rules/` endpoint (see below):

```
patient_name      Patient name                #6A3FA0
physician_name    Physician / provider name   #9B6FD1
person_name       Other person name           #7C4DBC
guarantor_name    Guarantor / next of kin     #7C4DBC
facility_name     Facility / organization     #3A7CA5
employer          Employer                    #3A7CA5
date_of_birth     Date of birth               #B8792D
date_of_service   Date of service             #B8792D
other_date        Other date                  #B8792D
age_over_89       Age above 89                #B8792D
age_89_or_below   Age 89 or below             #B8792D
street_address    Street address              #2D6FB8
zip_code          ZIP code                    #2D6FB8
phone             Telephone                   #1F8A70
fax               Fax                         #1F8A70
email             Email                       #1F8A70
url               URL                         #2D6FB8
ssn               SSN / government ID         #A4291F
mrn               Medical record number       #A4291F
member_id         Member ID                   #A4291F
account           Account number              #8A5A1B
payment_card      Payment card / bank ID      #A4291F
ip_address        IP address                  #2D6FB8
device_id         Device identifier           #5B6770
license           Certificate / licence       #8A5A1B
vehicle           Vehicle identifier          #5B6770
biometric         Biometric identifier        #7C4DBC
photo             Full-face image             #7C4DBC
other             Other identifier            #5B6770
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
  detector: string;      // "pattern" | "heuristic" | "context" | "azure_ai_language" | "anthropic"
  block_index: number;   // index into DocumentPayload.blocks
}

type BlockPart =
  | { text: string }
  | { entity: string };  // entity `code`

interface DocumentBlock {
  index: number;
  page: number;
  type: 'title' | 'sub' | 'h' | 'p' | 'table_row';
  // OCR fallback tiers for a page with no usable native text layer, tried
  // in this order: 'tesseract' first, then 'azure_ocr' (Azure AI Document
  // Intelligence) as a last resort when enabled and Tesseract still comes
  // up short. Treat either as lower-reliability than 'text'.
  source: 'text' | 'tesseract' | 'azure_ocr';
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

Saves the upload with `status="queued"` and dispatches ingestion (extract text per page,
run PHI detection — the regex/heuristic engine, plus Azure AI Language and/or Claude when
enabled — create Entity rows and CategoryRule rows) as a Celery task. With no
`CELERY_BROKER_URL` configured (the default for local dev), the task runs synchronously
in-process before the response is returned, so `status` is already `"in_review"` (or
`"failed"`) by the time the client sees it — a deployment with a real broker returns
`"queued"` immediately instead, and the client should poll `GET /api/jobs/:id/` until the
status leaves `"queued"`/`"scanning"`.

Each detected entity's default `mode` is `preset` if its confidence is at or above the
job's `confidence_threshold` (0.85 by default), otherwise `"keep"` — a low-confidence
guess is always visible for review, but never changes the document until a reviewer
confirms it.

If the PDF can't be parsed (encrypted, no extractable text, corrupt) or an enabled AI
detector is misconfigured, the Job ends up with `status="failed"` and a human-readable
`error_message`. Returns `201 { job: Job }` in every case (the failure is reported on the
Job, not as a non-2xx response).

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
`true`, returns `409 { detail, unresolved_count }`.

Otherwise: sets `status="finalizing"`, then true-redacts the *original* PDF's content
stream via PyMuPDF (burning in every non-`"keep"` entity's approved mode — not the
reportlab reconstruction the export endpoint below uses), then re-runs detection on the
finalized document as a second-pass verification. If anything that should have been
removed is still detectable there, the job is left recoverable: `status` becomes
`"failed"` with an `error_message` describing the count (never the actual values), the
source file is **not** purged, and no audit trail is written — reopen the job, adjust
entities, and complete again. Returns `422 { detail, job: Job }` in that case.

On success: writes one permanent `AuditRecord` row per entity (see `GET .../audit/`
below), stores the finalized PDF as the canonical `"pdf"` export artifact, sets
`status="complete"`, purges the source file, and returns `200 { job: Job }`.

### `POST /api/jobs/:id/reopen/`
Sets `status="in_review"`. Returns `200 { job: Job }`.

### `GET /api/jobs/:id/audit/`
Returns `200 { rows: AuditRow[] }`, ordered by entity `code`. Before completion, these
rows are a live preview derived from the (still-editable) Entity table. After completion,
they're read from the permanent `AuditRecord` table instead — written once at
finalization and append-only from then on (an update or delete attempt raises at the
model layer; nothing in the API can trigger one).

### `POST /api/jobs/:id/export/`
Body: `{ formats: Array<'pdf'|'csv'|'json'> }`. Generates the requested artifacts server
side and returns `200 { files: ExportFile[] }`. The `"csv"` (audit trail) and `"json"`
(entity manifest) formats are hash-only reconstructions from the block/entity model, same
as before. The `"pdf"` format is the true-redacted document from `/complete/` when the job
is already complete (or already finalized once); requesting it before completion falls
back to a reportlab reconstruction from the same block/entity model the Review screen
renders, since the original file's content stream isn't touched until completion.

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
