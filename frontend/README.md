# PHI De-Identification — Frontend

A React + TypeScript single-page app for the HIPAA Safe-Harbor PHI de-identification
workflow: upload a PDF, scan it for the 18 Safe Harbor identifier classes, set default
handling rules per category, review every detected entity side-by-side against the
original document, then export a de-identified PDF plus an audit CSV and entity
manifest JSON.

## Setup

```bash
npm install
cp .env.example .env   # optional — only needed if the API isn't at the default URL
npm run dev
```

The dev server runs on `http://localhost:5173`. By default the app talks to the Django
API at `http://localhost:8000/api`; override this with `VITE_API_BASE_URL` in `.env`.

## Scripts

- `npm run dev` — start the Vite dev server.
- `npm run build` — type-check (`tsc -b`) and produce a production build in `dist/`.
- `npm run preview` — serve the production build locally.
- `npm run lint` — run oxlint.

## Architecture

The app is a plain Vite + React Router SPA with no server-side rendering and no global
state library: each routed screen (`src/pages/`) owns its own data fetching against a
small typed API client (`src/api/client.ts`, built on `fetch`, throwing a typed
`ApiError` with the backend's `detail` message on any non-2xx response) and the shared
response/entity shapes in `src/api/types.ts` mirror the backend contract field-for-field.
Cross-cutting UI — the nav rail, status/category/mode badges, loading/error/empty
states, the document panes, and the entity inspector — lives in `src/components/` and is
styled entirely through CSS custom properties in `src/theme.css` (dark nav rail, cream
content background, IBM Plex Sans/Serif/Mono) so the visual language for a given mode
(redact/mask/pseudonymize/keep) is defined once and reused identically by the entity
list's mode pills and the document pane's inline span styling. The review screen is the
only screen with meaningfully complex state: it holds the job's entities in local state,
applies optimistic updates on single/bulk mode changes (rolling back on API failure),
and resolves each entity's on-page rendering (redacted block / masked pill / pseudo text
/ kept text) from the entity's `mode` plus the category's configured token from
`/rules/`.

## Judgment calls made against the API contract

These weren't fully specified in the contract and were resolved with a reasonable
default — flag them for reconciliation with the backend:

- **`confidence_threshold` has no update endpoint.** The contract exposes
  `Job.confidence_threshold` but there's no `PATCH` to change it. The Rules screen shows
  a threshold slider, but it only controls a *client-side* display threshold (persisted
  per-job in `localStorage`, see `src/lib/threshold.ts`) that dims low-confidence spans
  in the Review screen — it never calls the API. If the backend later exposes a way to
  set this, the slider should start calling it instead.
- **Mask-mode token source on the Review screen.** `Entity` doesn't carry a `token`
  field, so the de-identified pane looks up the token from the job's `CategoryRule` (via
  `GET /jobs/:id/rules/`) fetched alongside the document, falling back to
  `[CATEGORY]` if a category is somehow missing from that response.
  `src/lib/categories.ts` also has a hardcoded `DEFAULT_TOKENS` map used only for the
  upload-preset UI copy, not for rendering.
- **Failed jobs (`status: "failed"`) aren't given a dedicated route.** The contract
  doesn't describe a screen for a failed job — the Queue page instead renders the row
  as non-clickable and shows `error_message` inline in the "PHI found" column.
  Kept documents can revisit an existing review via `/jobs/:id/review`; the queue
  routes each job to a screen picked from its `status` (`scanning` → rules,
  `in_review` → review, `complete` → audit).
- **Upload preset picker is limited to `redact` / `mask` / `pseudo`** (excluding
  `keep`) since a "keep everything by default" preset doesn't fit a Safe-Harbor
  workflow — this matches the task brief's explicit list, though `Mode` as a type
  technically allows `keep` too.
- **`bulk_update` toolbar actions** ("Redact all" / "Mask all" / "Pseudonymize all" on
  the Review screen) call `POST /jobs/:id/entities/bulk_update/` with no `category`,
  i.e. they apply to every entity in the job, matching the contract's description of
  omitting `category`. There's no per-category "bulk" button in the toolbar since the
  Rules screen already offers per-category default modes.
- **`complete` conflict flow**: on a `409` from `POST /jobs/:id/complete/`, the UI reads
  `unresolved_count` off the error body (typed as `Record<string, unknown>` extras on
  `ApiError.body`) and shows an inline "N entities kept as-is — complete anyway?"
  banner that retries with `force: true` rather than a browser `confirm()`.
