# Administration Control Plane Acceptance

Date: 26 August 2026 (Asia/Kolkata)

## Accepted scope

The admin role now has a dedicated governance interface and seven RBAC-protected
API operations. It is not an elevated version of the citizen chatbot.

### Professional account lifecycle

- List police and advocate accounts with active state and owned-case count.
- Create controlled police or advocate accounts. Public registration is now
  citizen-only and cannot self-assign police, advocate or administrator access.
- Suspend or reactivate accounts. Suspension immediately blocks password login,
  access-token use and refresh-token rotation.
- Change police/advocate role only when the account owns zero cases. This avoids
  making existing private case data cross a role boundary.
- Administrator and citizen accounts cannot be mutated through the professional
  account endpoint.
- Every mutation creates an append-only audit event.

### Governed global-corpus expansion

The workflow is deliberately staged:

1. **Stage** an official PDF with title, source type, jurisdiction, issuing
   authority and an HTTPS official source URL.
2. Verify the 30 MiB limit, PDF signature and SHA-256 uniqueness before writing
   the versioned object to the corpus S3 bucket.
3. **Validate** extraction/OCR quality and record pages, characters and OCR page
   count. Sources with insufficient legal text are rejected.
4. **Publish** only a validated source. BGE-M3 dense+sparse embeddings are stored
   in `global_legal_corpus` with `corpus_tier=extended`,
   `verified_official=true` and `quality_status=admin_validated`.
5. Fast, Deep, drafting and defence retrieval search verified Gold plus governed
   extended sources. The original Gold manifest and its strict 25,517-point
   validation baseline remain unchanged.

Exact-file duplicates are rejected before upload. Gold cannot be overwritten
from the admin UI.

## Interface

The administration workspace includes:

- active police/advocate and corpus-queue metrics;
- professional account provision and suspension controls;
- official-source PDF intake form;
- staged/validated/rejected/published governance queue;
- latest audit events and actors;
- admin-specific navigation and `C` workspace shortcut.

## Verification

- Complete backend suite: **101 passed** in 13.32 seconds.
- Admin lifecycle/corpus focused suite: **2 passed**.
- Next.js 14 type, lint and production static export: **passed**.
- Reversible Alembic migration `c31476d8ca22`: **applied at head**.
- Live corpus status: **381/381 Gold documents, 25,517/25,517 Gold points,
  validation pass, 0 extended points before the first real admin publication**.
- Authenticated admin browser QA: command centre and operations workspace passed.
- Browser console: **zero warnings and zero errors**.
- Disposable admin and its audit record removed; zero QA admins remain.

## Bootstrap the first administrator

This is the only manual action. The command prompts twice and never places the
password in shell history:

```bash
cd "/Users/sripathidhruvreddy/Documents/MAJOR PROJECT"
set -a
source .env
set +a
export DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:${POSTGRES_PORT:-5432}/${POSTGRES_DB}"
PYTHONPATH="$PWD/backend" .venv-ingest/bin/python scripts/create_admin_account.py \
  --name "Platform Administrator" --email admin@example.com
```

The bootstrap script refuses to create a second administrator. Sign in at
`http://localhost:3000`, open **Administration**, and provision police/advocate
accounts there.

## API surface

- `GET /admin/overview`
- `GET|POST /admin/users`
- `PATCH /admin/users/{user_id}`
- `GET|POST /admin/corpus/intakes`
- `POST /admin/corpus/intakes/{intake_id}/validate`
- `POST /admin/corpus/intakes/{intake_id}/publish`
- `GET /admin/audit`
