# Corpusil

*The single picture: what it is, where it stands, what the finished product is,
and the order we build it in. Written 9 October 2026, with the v5 corpus build
at 799 of 1,563 documents.*

Read this first. Three other documents go deeper and none of them contradict
this one:

| Document | For |
|---|---|
| [PRD.md](PRD.md) | How the system works — architecture, ingestion, retrieval, the agent graph, verification |
| [OPERATIONS.md](OPERATIONS.md) | How to run it — build the corpus, start the stack, cut a desktop release |
| [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md) | The release gates and the measurements a milestone must pass |

---

## 1. What Corpusil is

A legal intelligence system for India that answers a question **and shows you
the law it relied on**, for four kinds of user: a citizen, a police officer, an
advocate, and an administrator.

The distinguishing property is not the answer. It is what the system does when
it cannot answer well:

- every material claim is tied to a passage actually retrieved from the corpus
- every citation opens at the page of an official source
- repealed, superseded and uncommenced law is labelled as such, in every lane
- when the corpus cannot support an answer, it refuses instead of guessing
- one user's case material is never reachable from another's question

**This is the product.** Features are built on top of it and none may bypass
it. A feature that would is cut rather than weakened.

### What it refuses to be

It does not predict outcomes, does not tell anyone they will win, does not
file anything, and does not replace a lawyer. It gives legal *information*
with its sources, and says so.

---

## 2. Where it stands today

| | |
|---|---|
| Backend tests | **902** across 117 files |
| Frontend tests | 6 suites |
| API endpoints | 58 across 16 routers |
| Corpus (manifest) | 1,566 rows / **1,563 unique documents** / 55,382 pages |
| Judgments in corpus | **93** (79 Supreme Court, 14 AP High Court) |
| Jurisdictions | 1,260 Central · 288 Andhra Pradesh · 18 Telangana |
| Source URLs missing | 0 · not verified official: 0 · OCR outstanding: 0 |
| Live corpus | `global_legal_corpus_v4` serving; **v5 building**, 799/1,563, zero failures |
| Release gates | 7, in one command, plus a volume-vs-ranking analysis |
| Desktop | Tauri, three targets, signed updater |

### Measured performance

| | Fast | Deep |
|---|---|---|
| p50 | **0.03 s** | 64.95 s |
| p95 | 0.18 s | 142.47 s |
| Time to first useful output | 0.03 s | **0.57 s** (was 64.66 s) |

Deep latency is **97% language model**. Orchestration is 0.1 s of 65 s — there
is no queue, no idle wait and no cold start to remove. With a model downgrade
ruled out on quality grounds, the honest lever was perceived latency: Deep now
publishes located authorities in half a second instead of showing nothing for
a minute. The 142 s p95 is the verification retry pass, which fires on roughly
one query in seven.

---

## 3. What is built

### The trust layer
Hybrid dense and sparse retrieval with server-side fusion · claim-to-passage
grounding · openable page-linked citations · repeal and currency labelling
unified across every lane · IPC→BNS, CrPC→BNSS, IEA→BSA section mapping ·
conservative abstention · case-scope isolation that fails closed · a
verification pass with retry.

### Platform
Register, login, cookie sessions, refresh-token rotation with reuse detection,
token revocation · four roles with enforced permissions · rate limiting ·
audit log · Fast and Deep lanes with Auto routing · durable Deep jobs with
progress · chat history with stable ordering · document upload, object storage
and per-case private indexing · command palette · desktop app with readiness
check and updater · voice input (English India) · feedback.

### Citizen
Plain-language answers with citations · both lanes · emergency and refusal
screening · abstention on corpus gaps · per-section grounding under each
answer · source inspector · document upload and analysis · session history ·
follow-up routing.

### Police
Case register with proven isolation · evidence upload · FIR fact extraction
and drafting · specialist prompt profiles · **statutory investigation
timeline** — nine BNSS deadlines, persisted, with real calendar-month
arithmetic · **BNSS compliance record** across arrest, search and seizure,
case diary and final report — 24 requirements plus four conditional ·
citation currency check.

### Advocate
Case corpus · defence strategy with two-sided analysis and adverse arguments ·
authority mapping · citation currency check · four specialist personas
selected deterministically (defence strategy, authority mapper, evidence
challenge, precedent comparator).

### Admin
User management · provisioning police and advocate accounts · corpus intake
with checksum and signature verification, validate and publish · corpus
statistics · ingestion progress · audit log. Deliberately **cannot** reach
private case material through a general search.

---

## 4. What is not built — honestly

### Three blind spots that outrank any feature

**1. The corpus is the ceiling.** 93 judgments cannot support precedent
research, a citator, case comparison or checking an opponent's authorities.
Coverage is Central plus Andhra Pradesh, so a citizen in any other state gets
nothing state-specific on tenancy, land, police rules or welfare. This is an
acquisition problem, which is why it is easy to leave off a feature list — and
it decides whether half the features work at all.

**2. Nothing keeps the law current.** There is no pipeline for amendments,
notifications or new judgments; ingestion is a manual full rebuild. A legal
product that does not update is *wrong* within months, silently.

**3. Compliance is an obligation, not a feature.** Under the DPDP Act 2023,
consent notices, purpose limitation, data-principal rights, a retention
schedule, a grievance officer and breach notification are mandatory. Citizens
upload FIRs and police upload case material. None of this exists, and the
privacy notice has nowhere to live because there is no public website.

### There is no public website
An unauthenticated visitor today gets a login box. No landing page, no install
page, no privacy policy, no terms.

### Platform gaps
No password reset, no email verification, no MFA · no answer export or print ·
history is not searchable · Deep progress polls instead of using the SSE events
the backend already emits · no human fallback when the system abstains.

### By role
**Citizen** — rights explainer · forum and limitation router · drafting beyond
FIR facts · upload redaction · multilingual · guided journeys · legal aid
referral.
**Police** — nothing beyond the BNSS: no state police manual coverage, no
court-stage tracking · drafting is FIR-only · deadlines are computed but never
surfaced as a register.
**Advocate** — no bail workflow at all · no drafting library · the debate room
is parked · everything precedent-related is blocked on the judgment corpus.
**Admin** — gates and rebuilds are CLI-only, so releasing is a terminal
command one person can run · no answer-quality visibility · no feedback
triage.

---

## 5. The finished product

Feature identifiers. `PRD.md` already cites C-02, C-04, C-05, C-06 and C-07;
those keep their meaning. The rest of the catalogue was never written down,
and is set out here.

### Platform — PLAT
| ID | Feature | State |
|---|---|---|
| PLAT-01 | Accounts, roles, sessions, rate limiting, audit | built |
| PLAT-02 | Trust layer: grounding, citations, currency, abstention, isolation | built |
| PLAT-03 | Fast and Deep lanes, durable jobs | built |
| PLAT-04 | Account recovery: email verification, password reset, MFA for professionals, device list | **to build** |
| PLAT-05 | DPDP compliance: consent, data-principal rights, retention, erasure, grievance officer | **to build** |
| PLAT-06 | Export and print an answer with citations intact | **to build** |
| PLAT-07 | Searchable history: find, pin, rename, organise by matter | **to build** |
| PLAT-08 | Deep progress over SSE instead of polling | **to build** |
| PLAT-09 | Human fallback on abstention — route to legal aid or a panel advocate | **to build** |
| PLAT-10 | Offline desktop with a local corpus pack | partial |
| PLAT-11 | Accessibility and low bandwidth | **to build** |
| PLAT-12 | Information-not-advice framing, Bar Council constraints respected | **to build** |

### Website — WEB
The product has no public face. It also has nowhere to publish the privacy
notice DPDP requires, which makes this a compliance dependency and not only
marketing.

| ID | Feature | State |
|---|---|---|
| WEB-01 | Landing page: what it is, who it is for, and the trust story — shown instead of a login box | **to build** |
| WEB-02 | Install page: macOS, Windows and Linux builds from the release workflow, with checksums and what each needs | **to build** |
| WEB-03 | Privacy notice and terms — the DPDP consent notice and grievance officer live here | **to build** |
| WEB-04 | Help and how-to-use, per role | **to build** |
| WEB-05 | Route split: the app moves off `/` so the landing page can own it | **to build** |

### Citizen — C
| ID | Feature | State |
|---|---|---|
| C-01 | Ask in plain language or by voice; answer with openable citations | built |
| C-02 | Upload redaction before analysis | **to build** |
| C-03 | Notice and summons explainer: what it demands, the deadline, the risk | **to build** |
| C-04 | Rights explainer — arrest, stop, summons; offline and printable | **to build** |
| C-05 | Forum and limitation router: where to go, by when, what it costs | **to build** ⚠ |
| C-06 | Drafting beyond FIR facts: complaint, RTI, consumer complaint, legal notice | **to build** |
| C-07 | Multilingual | **to build** |
| C-08 | Guided journeys for the situations people actually arrive with | **to build** |
| C-09 | Legal aid referral — eligibility and the DLSA to approach | **to build** |
| C-10 | My matter: deadlines and reminders for their own situation | **to build** |

⚠ C-05 carries real liability. A wrong limitation period loses a case. It must
cite the limitation provision, show its basis, and abstain rather than guess.

### Police — P
| ID | Feature | State |
|---|---|---|
| P-01 | Case register with proven isolation, evidence upload | built |
| P-02 | FIR fact extraction and drafting | built |
| P-03 | Statutory investigation timeline, nine BNSS deadlines | built |
| P-04 | BNSS compliance record, 24 requirements plus four conditional | built |
| P-05 | Deadline **register**: due, overdue, breached, across cases | **to build** |
| P-06 | Compliance as a record: date and evidence attached per duty | **to build** |
| P-07 | Drafting set: s.35(3) notice, s.94 production order, seizure memo, case diary, remand application, chargesheet skeleton on s.193(3) heads | **to build** |
| P-08 | Offence ingredient checklist — does the evidence establish each element | **to build** |
| P-09 | Search and seizure legality check (s.103/105) | **to build** |
| P-10 | Evidence inventory, chain of custody, witness tracker | **to build** |
| P-11 | Supervisory view: unit-wide compliance and imminent breaches | **to build** |
| P-12 | Court-ready case file export | **to build** |

### Advocate — A
| ID | Feature | State |
|---|---|---|
| A-01 | Case corpus, defence strategy with adverse arguments, authority mapping | built |
| A-02 | Bail: regular, anticipatory, default, s.479 undertrial release | **to build** |
| A-03 | Drafting library with authorities inserted from retrieval | **to build** |
| A-04 | Matter calendar: limitation and hearing dates | **to build** |
| A-05 | Brief and synopsis generation | **to build** |
| A-06 | Precedent research by court, year and holding | blocked on CORP-01 |
| A-07 | Is this still good law — judgment citator | blocked on CORP-03 |
| A-08 | Check the opponent's cited authorities | blocked on CORP-01 |
| A-09 | Case comparison on facts | blocked on CORP-01 |
| A-10 | The debate room | parked |

### Admin — AD
| ID | Feature | State |
|---|---|---|
| AD-01 | User management, corpus intake, statistics, audit log | built |
| AD-02 | Release console: run the gates, read results, approve or refuse a cutover, roll back | **to build** |
| AD-03 | Corpus coverage browser; currency flags; OCR and verification queues as work lists | **to build** |
| AD-04 | Answer-quality dashboard: abstention, citation coverage, unsupported claims, latency, over time | **to build** |
| AD-05 | Feedback triage and incident handling: trace a bad answer to its chunks, quarantine a document | **to build** |
| AD-06 | Full user management: suspend, force reset, role change, MFA enforcement | **to build** |
| AD-07 | Data retention and deletion honoured end to end | **to build** |
| AD-08 | Model and prompt configuration with A/B comparison | **to build** |

### Corpus — CORP
| ID | Feature | State |
|---|---|---|
| CORP-01 | Judgments at volume: Supreme Court and every High Court served | **to acquire** |
| CORP-02 | State law for every state claimed | **to acquire** |
| CORP-03 | Overruling and subsequent-history data | **to acquire** |
| CORP-04 | Incremental ingestion — add, replace, retire without a rebuild | **to build** |
| CORP-05 | Amendment and notification watch | **to build** |
| CORP-06 | "The law you relied on changed" — notify recipients of a superseded citation | **to build** |
| CORP-07 | Golden set v4: document identities instead of phrase predicates | **to build** |
| CORP-08 | Proactive expert review on sampled answers | **to build** |

---

## 6. The plan

Lanes follow the existing split. **Codex** owns corpus acquisition, metadata,
source verification, documentation and release evidence. **Claude** owns
backend, retrieval, answer quality and the application.

The ordering contradicts the instinct to build features first, deliberately:
building the advocate lane against 93 judgments would waste months.

### Phase 0 — Close out v5
Triggers the moment the build finishes. Everything here already exists; this
phase runs it.

1. Confirm the worker and keeper have exited and the host is idle. Every gate
   is a measurement and a busy host invalidates it.
2. `scripts/run_corpus_gates.sh global_legal_corpus_v5 v5-cutover`
3. Analyse failures **separating volume from ranking**. v5 is roughly twice
   v4's size, so recall and citation numbers move on volume alone. Only items
   whose haystack did not grow support a claim about retrieval. Never
   `--record` a baseline over a failing gate.
4. Close the known payload gaps: `ocr_required` and `currency_note` backfill
   for early points; prune the 129 citation-furniture and 36 doubled-text
   chunks after review; re-extract the three doubled-text documents.
5. Re-run the gates. Cut over only on a clean pass, reviewed by Codex.
6. Set `max_length` from measured data — 8,192 today, longest real chunk
   64,802 characters.

**Done when:** seven gates pass, v5 serves, v4 retained for rollback, evidence
written under `docs/evidence/gates/v5-cutover`.

### Phase 1 — Keep the law current
CORP-04 · CORP-05 · CORP-06 · CORP-07 · CORP-08

Highest value after cutover, because without it everything decays and nobody
notices. Incremental ingestion also removes the full-rebuild cost that makes
every corpus change a day-long operation. CORP-07 matters more than it looks:
recall@5 once read 0.927 while the governing provision was absent from the top
100, because the golden set matches phrases rather than documents.

### Phase 2 — Corpus breadth *(Codex)*
CORP-01 · CORP-02 · CORP-03

Acquisition, not engineering. **Licensing review happens before acquisition,
not after** — judgment text and commercial headnotes have different terms.
Without CORP-03 the citator is not possible and must not be promised.

### Phase 3 — Foundations and the public face
PLAT-04 · PLAT-05 · PLAT-06 · PLAT-07 · PLAT-08 · PLAT-09 · PLAT-12 ·
WEB-01 · WEB-02 · WEB-03 · WEB-04 · WEB-05

Nothing role-specific ships before these. PLAT-05 and WEB-03 are coupled: the
DPDP consent notice has to be published somewhere, and that somewhere is the
website. WEB-05 is a routing change — the app moves off `/` so the landing
page can own it; the frontend is a static export, so the pages themselves are
cheap, and the install page links the artifacts the release workflow already
builds for three desktop targets.

### Phase 4 — Role features
**4a. Admin** — AD-02 first. Until it exists, releasing is a terminal command
one person can run, and that person is a bottleneck on their own product.
Then AD-03, AD-04, AD-05, AD-06, AD-07.

**4b. Police** — most value for least new code, because the deadline engine is
already the best-engineered thing in the product and never leaves the function
that computes it. P-05, P-06, P-07, P-08, P-09, P-10, P-11, P-12.

**4c. Citizen** — C-03, C-09, C-04, C-08, C-06, C-02, C-10, then **C-05 last**
in this group, by its risk.

**4d. Advocate** — A-02, A-03, A-04, A-05. A-06 to A-09 do not start before
Phase 2 delivers.

### Phase 5 — Reach
C-07 multilingual · voice out · PLAT-10 offline · PLAT-11 accessibility.

Last by the product owner's decision: features first, then the multiplier. The
answer is translated; the law is quoted in its original text and never
paraphrased in translation.

---

## 7. Decisions that are the owner's, not engineering's

Work on these should not start before the decision is made.

| Decision | Why it is yours |
|---|---|
| How conservative C-05 limitation guidance must be | A wrong number loses a case |
| Whether to acquire judgment and overruling data | Decides whether A-06 to A-09 exist at all |
| Which states the product claims to serve | Decides CORP-02 scope |
| Whether any query may leave the device | A hosted model is a privacy policy decision before an engineering one |

---

## 8. What we will not build

- **Outcome prediction** — unverifiable, and harmful in a legal tool
- **E-filing and court-portal integration** — brittle, high maintenance, no
  corpus advantage. Read-only case-status lookup is the one defensible
  exception.
- **Lawyer marketplace, social features, gamification** — a different product
- **Anything that paraphrases the law in translation**

---

## 9. The one-sentence version

Corpusil's advantage is not that it answers legal questions — it is that it
**tells you when it does not know, and shows you the actual page when it
does**. Everything above exists to protect that.
