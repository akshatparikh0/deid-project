# PHI De-Identification

A HIPAA Safe Harbor (45 CFR §164.514(b)(2)) document de-identification tool:
upload a PDF, it's scanned for the 18 canonical identifier classes (names,
dates, SSNs, MRNs, addresses, contact info, device/vehicle/license IDs, IPs,
URLs, biometrics, photos, …), a reviewer decides per-entity or per-category
whether each is redacted, masked, pseudonymized, or kept, and the tool
exports a de-identified PDF plus an audit trail (hashes only — never
plaintext) and an entity manifest.

- **Backend** — `backend/` — Django + Django REST Framework. The entire
  pipeline (detection, extraction, true PyMuPDF redaction, verification)
  lives in the `documents` app — see `backend/README.md` for architecture
  notes and known simplifications.
- **Frontend** — `frontend/` — React + TypeScript (Vite, react-router-dom).
  See `frontend/README.md` for architecture notes and judgment calls made
  against the API contract.
- **Infrastructure** — `infra/` (Bicep, Azure) and `docker-compose.yml` /
  `.github/workflows/ci.yml` — see [Deployment](#deployment) below.

## Run it

One-time setup:

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
deactivate
cd ../frontend
npm install
```

Then, from the project root, a single command starts both the API (:8000)
and the frontend (:5173), and Ctrl+C stops both:

```bash
./dev.sh
```

Open `http://localhost:5173`, upload a PDF, and walk through
Rules → Review → Complete → Export. Everything runs synchronously
in-process against local disk + SQLite by default — no broker, database
server, or cloud credentials needed for this path; upload processing, true
PDF finalization, and second-pass verification all happen inline, the same
way they would with a real Celery worker and Postgres behind them (see
Deployment).

## API contract

The full request/response contract both sides were built against lives at
[`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) — the definitive reference
for endpoint shapes, field names, and status codes.

## Deployment

- **Docker Compose** (`docker-compose.yml`) — Postgres + Redis + the Django
  API + a Celery worker + the built frontend behind nginx, for exercising
  the async/multi-service path locally before it ships:
  `cp backend/.env.example backend/.env && docker compose up --build`.
  `docker-compose.staging.yml` overlays pre-built registry images instead
  of building locally.
- **CI** (`.github/workflows/ci.yml`) — Django tests, the standalone
  pipeline's pytest suite, a frontend typecheck + build, both Docker images,
  and a Bicep compile check, on every push/PR.
- **Azure infrastructure** (`infra/main.bicep`) — provisions every FR-54 –
  FR-66 component (Container Apps, Service Bus, PostgreSQL Flexible Server,
  Key Vault, Document Intelligence, AI Language, Blob Storage, private
  networking end to end). Compiles cleanly (`bicep build`) but **has not
  been deployed against a real Azure subscription** — see `infra/README.md`
  for the deploy command, the two manual steps Bicep can't automate
  (Entra ID app registration, the HIPAA BAA), and a note on hardening audit
  trail immutability at the database level.
