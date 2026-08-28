# Role-Curated Experience and Agent Acceptance

Date: 26 August 2026 (Asia/Kolkata)

## Accepted role boundaries

| Role | Interface | Agent contract | Private data access | Professional tool |
| --- | --- | --- | --- | --- |
| Citizen | Rights-and-procedure command centre | Practical steps, required facts/documents, clear uncertainty | No police or advocate collection | Procedure Navigator, Rights Explainer, Authority Finder |
| Police | Investigation command centre and police case operations | Procedure, evidence gaps, factual fidelity and safeguards | Owned police matters only | FIR Review, Evidence Integrity, Procedure Compliance, Case Evidence Search |
| Advocate | Authority command centre and client-matter strategy | Two-sided issue/rule/application, adverse authority and lawful counterarguments | Owned advocate matters only | Defence Strategy, Authority Mapper, Evidence Challenge, Precedent Comparator |

All roles share the verified Gold legal corpus. Private retrieval is additive
only for an explicitly selected, owned professional matter. It never replaces
the public authority layer and never crosses police/advocate collection
boundaries.

## Implementation

- The product opens on a role-specific command centre, not a generic chatbot.
  Each command centre has a distinct executive headline, operational metrics,
  agent directory, recommended workflow, primary actions and privacy notice.
- The permanent navigation changes by role: `Legal research` for citizens,
  `Investigation research` and `Police case operations` for police, and
  `Authority research` and `Advocate case strategy` for advocates.
- `CommandPalette` provides a searchable keyboard-first launcher. Global
  shortcuts are `Command/Ctrl+K` (palette), `D` (dashboard), `R` (research),
  `N` (new research), and `C` (professional case operations).
- Police and advocate case operations expose separate agent launchers,
  terminology, matter copy, evidence classifications, prompts and primary
  analysis tools. They are operational workspaces rather than chat skins.
- The frontend derives navigation, headings, descriptions, suggestions,
  placeholders, evidence classifications and professional tools from the
  authenticated role.
- Deep Auto routing is case-aware. A case-linked question selects Deep.
- The Deep retrieval agent searches Gold plus exactly one role collection with
  an exact `case_id` filter for police and advocate users.
- Citizen chat cannot target either private collection, even if a `case_id`
  reaches the agent state.
- Role-specific objectives, output contracts and safety boundaries are injected
  into the LangGraph state before query understanding and reasoning. A
  deterministic role-bounded specialist router selects the operational sub-agent
  from the query and case scope; that specialist objective is injected into both
  understanding and reasoning prompts. The trace records its ID and label.
- FIR drafting now requires `police:investigation:own`; advocate defence
  analysis requires `advocate:strategy:own`.
- Ownership, case-role match, collection isolation and every decision remain
  enforced server-side; hiding a UI button is not treated as authorization.

## Interface acceptance matrix

| Capability | Citizen | Police | Advocate |
| --- | --- | --- | --- |
| Command-centre promise | Understand rights and next steps | Procedure-led, defensible investigation | Two-sided argument and authority verification |
| Research agent label | Citizen Legal Navigator | Police Procedure Research Agent | Advocate Authority Research Agent |
| Case workspace | Hidden and server-forbidden | Investigation matters | Client matters |
| Private search | None | Gold + owned police matter | Gold + owned advocate matter |
| Evidence intake | None | Complaint/FIR, statement, seizure memo, medical/forensic, digital evidence | Client statement, pleading, opposing filing, exhibit, order/judgment |
| Primary professional tool | None | Grounded FIR drafting/review | Grounded two-sided defence analysis |

## Verification

- Complete backend suite: **101 passed**; the role-specific acceptance captured
  here remains covered by that larger suite.
- Next.js 14 type check and static production export: **passed**.
- Focused role-specialist and legal-agent suite: **16 passed**; five parameterized
  scenarios prove distinct specialist selection.
- Live authorization matrix:
  - citizen case creation: `403`;
  - police case automatically typed `police`;
  - advocate case automatically typed `advocate`;
  - police read of own matter: `200`;
  - advocate read of police-owned matter: `403`;
  - police call to advocate strategy: `403`;
  - advocate call to police FIR drafting: `403`.
- Authenticated browser QA completed independently for citizen, police and
  advocate roles. All three command centres, the command palette, police case
  operations and advocate case strategy rendered correctly.
- Advocate browser console check: **zero errors and zero warnings**.
- Desktop visual acceptance confirms a corporate console layout: persistent
  navy navigation, restrained role accenting, information-dense hero metrics,
  agent cards and a workflow panel. Citizen/mobile navigation and the command
  palette were also verified.
- Docker backend, PostgreSQL, Qdrant and MinIO: healthy.
- All temporary role-QA users and their four audit records were deleted after
  verification; the database check returned zero disposable accounts.

## Key code locations

- `frontend/components/RoleDashboard.tsx`: role command centres and agent suite.
- `frontend/components/CommandPalette.tsx`: command search and shortcuts.
- `frontend/components/ProfessionalWorkspace.tsx`: police and advocate operations.
- `frontend/app/page.tsx`: role navigation, dashboard/research/workspace routing.
- `backend/app/agents/role_profiles.py`: role agent contracts.
- `backend/app/agents/orchestrator.py`: role-context LangGraph node and trace.
- `backend/tests/test_legal_agents.py`: role-context regression coverage.

## Create local professional accounts

Citizen self-registration is available in the UI. Police and advocate accounts
should be provisioned deliberately. The command prompts for the password without
echoing it or putting it in shell history:

```bash
set -a
source .env
set +a
export DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:${POSTGRES_PORT:-5432}/${POSTGRES_DB}"
PYTHONPATH="$PWD/backend" .venv-ingest/bin/python scripts/create_professional_account.py \
  --name "Demo Police Officer" --email officer@example.com --role police

PYTHONPATH="$PWD/backend" .venv-ingest/bin/python scripts/create_professional_account.py \
  --name "Demo Advocate" --email advocate@example.com --role advocate
```

This is the only manual step needed to see the professional interfaces with
your own accounts. Do not use shared credentials or real case evidence in demo
accounts.
