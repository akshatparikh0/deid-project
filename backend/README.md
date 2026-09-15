# PHI De-Identification — backend

Django + Django REST Framework API implementing a HIPAA Safe Harbor
(45 CFR §164.514(b)(2)) document de-identification workflow: upload a PDF,
detect the 18 canonical identifier classes, review/adjust how each one is
transformed, and export a de-identified PDF plus an audit trail.

## Setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

The API is now at `http://localhost:8000/api/`. Optionally
`python manage.py createsuperuser` to browse data at `/admin/`.

Scanned/image-only PDFs are OCR'd via Tesseract as a fallback when a page
has no native text layer. That requires the `tesseract-ocr` binary on the
server (the `pytesseract` *Python* package alone isn't enough):

```bash
sudo apt-get install tesseract-ocr   # Debian/Ubuntu
brew install tesseract                # macOS
```

If it isn't installed, text-layer PDFs still work fine — image-only pages
just fail extraction with a message saying so, same as before.

The defaults above work as-is for local development — no `.env` required,
no broker or cloud credentials needed, everything runs in-process against
local disk + SQLite. For anything beyond that (a shared/deployed instance),
copy `.env.example` to `.env` and set `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`,
and `DJANGO_ALLOWED_HOSTS` at minimum; see `.env.example` for every optional
AI detector, storage, and broker setting.

## Architecture

The entire pipeline lives in the `documents` Django app — one place to read
it end to end, one `detection.py`, one `extraction.py`, no second copy of
either under a different package. (An earlier iteration split this across a
standalone `redaction_pipeline` package and this app; it's been folded in.)

- **`documents/detection.py`** — the base PHI detector. It's regex +
  keyword-context based, not a trained NER model, so the project has zero
  *required* heavyweight ML dependencies. It handles the highest-precision
  identifiers well (SSNs, dates, emails, phone/fax, IPs, URLs, labelled
  record/member/account/license/vehicle/device numbers, US-style addresses,
  Luhn-validated credit card numbers, ages over 89) and falls back to
  lower-confidence heuristics for names (split into `patient_name` /
  `physician_name` / `guarantor_name` / other `person_name`, by nearby cue
  words), facilities, employers, biometrics, photos and the open-ended
  "other" class — the full taxonomy is `categories.py`'s `CATEGORY_ORDER`,
  shared with the project configuration schema.
  Overlapping matches are resolved by confidence first (not span length), so
  a short high-confidence match is never silently dropped in favor of a
  longer, vaguer one. When a piece of text is a table cell, its column
  header can be passed in to catch bare identifying values that have no
  inline label (see `extraction.py`'s table handling).
- **`documents/ai_detection.py`** — optional Azure AI Language and Claude
  detectors (FR-61), off by default (`REDACTION_ENABLE_AZURE_LANGUAGE` /
  `REDACTION_ENABLE_AI`). Each returns spans in the exact shape
  `detect_spans()` does; `detection.merge_spans()` resolves overlaps across
  every enabled engine together with the same confidence-first rule.
- **`documents/extraction.py`** — turns a PDF into paragraph-ish text blocks
  and table-row blocks via `pdfplumber`, using blank-line/heading heuristics
  since paragraph structure isn't reliably encoded in arbitrary PDFs. Tables
  are extracted row-by-row (via `page.find_tables()`) rather than folded
  into the surrounding paragraph text, so a "Relation"/"Name" pair (or any
  other row of related cells) stays adjacent for detection instead of being
  scattered by column-major reading order. Pages with no usable native text
  layer fall back through up to three OCR tiers in order: Tesseract, then
  (if `REDACTION_ENABLE_AZURE_OCR`) Azure AI Document Intelligence (FR-60)
  as a last resort.
- **`documents/ingest.py`** — orchestrates extraction → detection → creating
  `DocumentBlock`/`Entity`/`CategoryRule` rows. Runs as a Celery task
  (`documents/tasks.py`) dispatched from the upload view; with no
  `CELERY_BROKER_URL` configured it executes synchronously in-process
  (`CELERY_TASK_ALWAYS_EAGER`), so local dev needs no extra services, while
  a deployment with a real broker gets true async, queue-driven processing
  (FR-56/FR-57) for free from the same code. Each entity's default `mode` is
  the job's `preset` only if its detection confidence clears
  `Job.confidence_threshold`; below that it defaults to `"keep"` so a
  low-confidence guess never changes the document without a reviewer's
  confirmation (FR-21/AC-13).
- **`documents/surrogates.py`** — deterministic fake-value generation for
  "pseudonymize" mode (same input always maps to the same surrogate; no
  external `Faker` dependency).
- **`documents/finalize.py`** — reviewer-approved finalization (FR-76 –
  FR-83). Once a job is completed, this true-redacts the *original* PDF's
  content stream via PyMuPDF (`build_redacted_pdf`) — the text is removed,
  not painted over (FR-80) — rather than rebuilding the document. This is
  what `documents/complete.py` calls before the source file is purged.
- **`documents/verify.py`** — second-pass verification (FR-81, AC-25):
  re-runs detection on the finalized PDF and reports anything that should
  have been removed but is still readable. `documents/complete.py`
  orchestrates finalize → verify → write the permanent audit trail
  (`documents/audit.py`, one `AuditRecord` row per entity, append-only —
  `AuditRecord.save()`/`.delete()` refuse to change an existing row,
  NFR-16) → store the finalized PDF as the canonical export artifact. A
  verification failure leaves the job `"failed"` with the source file and
  every DB row untouched — reopen, adjust, and complete again.
- **`documents/export.py`** — generates the three downloadable artifacts on
  demand. The `"pdf"` format for a job that's already complete just returns
  the true-redacted artifact `finalize.py` already wrote; for a job still
  in review it's a lighter-weight reportlab reconstruction from the same
  block/entity model the Review screen renders (not a byte-level edit of
  the original file, since that file's content stream isn't touched until
  completion).
- **Storage adapters** (FR-67 – FR-75) — no dedicated module; provider
  selection lives entirely in `deid_backend/settings.py`'s `STORAGES` config
  (`STORAGE_PROVIDER=local|azure_blob|s3|gcs`, via `django-storages`) — no
  pipeline code names a provider (NFR-15), every file access goes through
  Django's `FileField` API regardless of backend.
- Source PDFs live under the configured storage's `uploads/` path and are
  deleted once a job is marked complete (`Job.purge_source_file`) — only the
  extracted blocks/entities and the permanent audit trail persist after
  that.
- Audit rows and the JSON export manifest store only a truncated SHA-256 of
  each identifier's original value, never the plaintext.

## Known simplifications

- The base detector is heuristic, not ML-based — expect it to miss unusual
  name formats or identifier styles it hasn't seen a pattern for, and expect
  the bare two-capitalized-word name heuristic to occasionally over-trigger.
  This is flagged per-entity via `detector: "pattern" | "heuristic" |
  "context" | "azure_ai_language" | "anthropic"` and a confidence score so a
  reviewer can prioritize what to double-check; enabling the Azure/Claude
  detectors improves recall on exactly the cases the regex engine misses.
- OCR'd blocks (`DocumentBlock.source in ("tesseract", "azure_ocr")`) are
  more error-prone than native text-layer extraction, and OCR'd pages don't
  get table-aware extraction (a scanned table is just OCR'd as loose
  paragraph text).
- Paragraph/heading detection from raw PDF text is heuristic; documents with
  unusual formatting may get body text classified as a heading or vice versa.
- `AuditRecord` immutability is enforced at the Django model layer
  (`save()`/`delete()` raise on an existing row) — real database-level
  append-only enforcement (a Postgres `REVOKE UPDATE, DELETE` grant) is a
  deployment-time hardening step; see `infra/`.
- Async processing and storage are both pluggable, but neither has been
  exercised against a real broker or cloud bucket in this repo's test suite
  (which runs everything in-process against local disk, by design, so it
  needs no external services) — validate `CELERY_BROKER_URL` and
  `STORAGE_PROVIDER` against a real deployment before relying on them.
