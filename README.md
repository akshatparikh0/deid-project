# PHI De-Identification

A HIPAA Safe Harbor (45 CFR §164.514(b)(2)) document de-identification tool:
upload a PDF, it's scanned for the 18 canonical identifier classes (names,
dates, SSNs, MRNs, addresses, contact info, device/vehicle/license IDs, IPs,
URLs, biometrics, photos, …), a reviewer decides per-entity or per-category
whether each is redacted, masked, pseudonymized, or kept, and the tool
exports a de-identified PDF plus an audit trail (hashes only — never
plaintext) and an entity manifest.

- **Backend** — `backend/` — Django + Django REST Framework. See
  `backend/README.md` for architecture notes and known simplifications.
- **Frontend** — `frontend/` — React + TypeScript (Vite, react-router-dom).
  See `frontend/README.md` for architecture notes and judgment calls made
  against the API contract.

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
Rules → Review → Export.

## API contract

The full request/response contract both sides were built against lives at
[`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) — the definitive reference
for endpoint shapes, field names, and status codes.
