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

The defaults above work as-is for local development — no `.env` required.
For anything beyond that (a shared/deployed instance), copy `.env.example`
to `.env` and set `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`, and
`DJANGO_ALLOWED_HOSTS` at minimum.

## Architecture

- **`documents/detection.py`** — the PHI detector. It's regex + keyword-context
  based, not a trained NER model, so the project has zero heavyweight ML
  dependencies and no model download. It handles the highest-precision
  identifiers well (SSNs, dates, emails, phone/fax, IPs, URLs, labelled
  record/account/plan/license/vehicle/device numbers, US-style addresses,
  Luhn-validated credit card numbers) and falls back to lower-confidence
  heuristics for names (split into `patient_name` / `physician_name` / other
  `name`, by nearby cue words), facilities, biometrics, photos and the
  open-ended "other" class. Overlapping matches are resolved by confidence
  first (not span length), so a short high-confidence match is never
  silently dropped in favor of a longer, vaguer one. When a piece of text is
  a table cell, its column header can be passed in to catch bare
  identifying values that have no inline label (see `extraction.py`'s table
  handling). Swap `detect_spans()` for a real NER/Presidio pipeline later
  without touching anything downstream.
- **`documents/extraction.py`** — turns a PDF into paragraph-ish text blocks
  and table-row blocks via `pdfplumber`, using blank-line/heading heuristics
  since paragraph structure isn't reliably encoded in arbitrary PDFs. Tables
  are extracted row-by-row (via `page.find_tables()`) rather than folded
  into the surrounding paragraph text, so a "Relation"/"Name" pair (or any
  other row of related cells) stays adjacent for detection instead of being
  scattered by column-major reading order. Pages with no usable native text
  layer are rasterized and OCR'd via Tesseract as a fallback.
- **`documents/ingest.py`** — orchestrates extraction → detection → creating
  `DocumentBlock`/`Entity`/`CategoryRule` rows. Runs synchronously in the
  upload request; at higher volume this is the natural place to hand off to
  a task queue (the `Job.status = "scanning"` state already models that).
- **`documents/surrogates.py`** — deterministic fake-value generation for
  "pseudonymize" mode (same input always maps to the same surrogate; no
  external `Faker` dependency).
- **`documents/export.py`** — generates the three downloadable artifacts.
  The de-identified PDF is *rebuilt* from the same block/entity model that
  drives the review screen (via `reportlab`), rather than trying to edit the
  original PDF bytes in place — that guarantees the export always matches
  exactly what the reviewer approved. It is not a pixel-identical
  reproduction of the source PDF's layout/fonts.
- Source PDFs live in `media/uploads/` and are deleted from disk once a job
  is marked complete (`Job.purge_source_file`) — only the extracted
  blocks/entities and the audit trail persist after that.
- Audit rows and the JSON export manifest store only a truncated SHA-256 of
  each identifier's original value, never the plaintext.

## Known simplifications

- Detection is heuristic, not ML-based — expect it to miss unusual name
  formats or identifier styles it hasn't seen a pattern for, and expect the
  bare two-capitalized-word name heuristic to occasionally over-trigger.
  This is flagged per-entity via `detector: "pattern" | "heuristic" | "context"`
  and a confidence score so a reviewer can prioritize what to double-check.
- OCR'd blocks (`DocumentBlock.source == "ocr"`) are more error-prone than
  native text-layer extraction — Tesseract misreads are possible, and OCR'd
  pages don't get table-aware extraction (a scanned table is just OCR'd as
  loose paragraph text).
- Paragraph/heading detection from raw PDF text is heuristic; documents with
  unusual formatting may get body text classified as a heading or vice versa.
- The de-identified PDF export is a faithful re-rendering of content and
  structure, not a byte-level edit of the original file's layout.
- Processing is synchronous per request — fine at demo/small-batch scale;
  a production deployment processing large batches should move `run_ingestion`
  onto a task queue.
