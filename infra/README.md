# Infrastructure

`main.bicep` provisions the Azure resources in requirements FR-54 – FR-66:
identity (Entra ID + a user-assigned managed identity), compute (Container
Apps), the ingest queue (Service Bus), the database (PostgreSQL Flexible
Server), secrets (Key Vault), OCR and detection (Document Intelligence +
AI Language), storage (Blob), telemetry (Log Analytics + Application
Insights), and networking (a VNet with a private endpoint in front of
every one of those services — public network access is off everywhere).

**This template has not been deployed against a real Azure subscription.**
It was authored and validated with `bicep build` (compiles cleanly to valid
ARM JSON, 40 resources, zero errors/warnings — see the repo's CI, which
does the same on every push), but that only proves it's syntactically and
type-correct, not that a live deployment succeeds end to end — a first real
deployment should go to a disposable resource group, not straight to
staging or prod.

## Deploying

```bash
az login
az group create -n rg-deid-staging-eastus2 -l eastus2
az deployment group create \
  -g rg-deid-staging-eastus2 \
  -f infra/main.bicep \
  -p infra/main.parameters.staging.json
```

Swap in `main.parameters.prod.json` for a production deployment (turns on
`zoneRedundant`, NFR-22). Both parameter files leave `apiImage` /
`workerImage` / `frontendImage` blank by default — a first deployment
provisions the infrastructure with no application revision running yet;
re-run the same deployment command with those three parameters (or
`-p apiImage=... workerImage=... frontendImage=...` inline) once
`.github/workflows/ci.yml` (or an equivalent) has pushed images to a
registry.

## What Bicep cannot do here

- **Microsoft Entra ID app registration (FR-55).** App registrations are a
  Microsoft Graph operation, not an ARM resource. Run once per environment:

  ```bash
  az ad app create --display-name deid-staging
  ```

  and wire the resulting application (client) ID into the API container's
  configuration (a Container Apps environment variable, not a Bicep param —
  it isn't a secret, but it is environment-specific).

- **The HIPAA Business Associate Agreement (FR-66).** A legal agreement
  with Microsoft covering the Azure subscription, not infrastructure.
  FR-66/AC-32 require this to exist *before* a project is created — no
  Bicep template can enforce that; it has to be a process/compliance
  checklist gate ahead of `az deployment group create`.

- **A customer-managed key for storage encryption.** The storage account
  deploys with Microsoft-managed encryption keys (FR-74's "encrypted at
  rest" requirement is satisfied either way). The project configuration
  schema's `storage.customer_managed_key` field (see the requirements
  document's specimen JSON) anticipates upgrading to one; doing so needs a
  Key Vault key plus an additional role assignment and is a reasonable
  next hardening step, not included here to keep the first deployment
  simpler to reason about.

## Database-level audit immutability

`documents.AuditRecord` (the backend's permanent, append-only audit trail —
see `backend/README.md`) enforces immutability at the Django ORM layer:
`save()` and `delete()` raise if a row already exists. That's real, but it
only holds as long as every write goes through Django — a direct SQL
connection to the Postgres database could still update or delete a row.
Hardening that at the database level, for a deployment that wants NFR-16 to
hold even against a compromised or careless direct-DB-access credential:

```sql
REVOKE UPDATE, DELETE ON documents_auditrecord FROM deid_app_role;
```

run once against the Postgres Flexible Server after migrations, using a
role distinct from the one Django itself connects as (which still needs
`INSERT` — bulk_create). This isn't automated in `main.bicep` because it
needs to run after `manage.py migrate` creates the table, not at
infrastructure-provisioning time; a natural place for it is a one-time step
in the deployment pipeline right after the `migrate` job.
