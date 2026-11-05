# 01 — Product

*What Corpusil is, where it stands, and every feature with its state.
Measured 9 October 2026, with the v5 corpus build at 801 of 1,563 documents.*

---

## 1. What it is, and what it refuses to be

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

It does not predict outcomes, does not tell anyone they will win, does not file
anything, and does not replace a lawyer. It gives legal *information* with its
sources, and says so.

Absolute zero hallucination cannot be guaranteed by a language model. The
enforceable target is **zero unsupported published claims in the evaluated
set**, backed by automatic abstention and visible uncertainty outside it.

---

## 2. Where it stands

| | |
|---|---|
| Backend tests | **1,351** collected from 942 functions (all passing, 4 November 2026) |
| Frontend tests | 6 suites |
| API endpoints | 58 across 16 routers |
| Corpus manifest | 1,566 rows / **1,563 unique documents** / 55,382 pages |
| Judgments | **93** (79 Supreme Court, 14 AP High Court) |
| Jurisdictions | 1,260 Central · 288 Andhra Pradesh · 18 Telangana |
| Source URLs missing | 0 · not verified official: 0 · OCR outstanding: 0 |
| Serving | `global_legal_corpus_v4` |
| Building | `global_legal_corpus_v5`, 801/1,563, zero failures |
| Release gates | 7 in one command, plus a volume-vs-ranking analysis |
| Desktop | Tauri, three targets, signed updater |
| Public website | **none** — an unauthenticated visitor gets a login box |

### 2.1 Measured performance

| | Fast | Deep |
|---|---|---|
| p50 | **0.03 s** | 64.95 s |
| p95 | 0.18 s | 142.47 s |
| Time to first useful output | 0.03 s | **0.57 s** (was 64.66 s) |

Deep latency is **97% language model**. Orchestration is 0.1 s of 65 s: no
queue, no idle wait, no cold start to remove. With a model downgrade ruled out
on quality grounds, the honest lever was perceived latency — Deep now publishes
located authorities in half a second instead of showing nothing for a minute.
The 142 s p95 is the verification retry pass, which fires on roughly one query
in seven.

---

## 3. The feature catalogue

Every feature has an identifier. Work refers to the identifier.

States: **built** · **to build** · **blocked** (waiting on something named) ·
**to acquire** (data, not code) · **parked** (decided against, for now).

### 3.1 Platform — PLAT

| ID | Feature | State |
|---|---|---|
| PLAT-01 | Accounts, roles, sessions, rate limiting, audit log | built |
| PLAT-02 | Trust layer: grounding, citations, currency, abstention, case isolation | built |
| PLAT-03 | Fast and Deep lanes, adaptive routing, durable jobs | built |
| PLAT-04 | Account recovery: email verification, password reset, MFA for professionals, device list | to build |
| PLAT-05 | DPDP compliance: consent, data-principal rights, retention, erasure, grievance officer | to build |
| PLAT-06 | Export and print an answer with its citations intact | to build |
| PLAT-07 | Searchable history: find, pin, rename, organise by matter | to build |
| PLAT-08 | Deep progress over SSE instead of polling | to build |
| PLAT-09 | Human fallback on abstention — route to legal aid or a panel advocate | to build |
| PLAT-10 | Offline desktop with a local corpus pack | partial |
| PLAT-11 | Accessibility and low bandwidth | to build |
| PLAT-12 | Information-not-advice framing; Bar Council constraints respected | to build |

### 3.2 Website — WEB

The product has no public face, and nowhere to publish the privacy notice DPDP
requires. That makes this a compliance dependency, not only marketing. The
frontend is already a static export, so the pages themselves are cheap.

| ID | Feature | State |
|---|---|---|
| WEB-01 | Landing page: what it is, who it is for, the trust story — shown instead of a login box | to build |
| WEB-02 | Install page: macOS, Windows and Linux builds, with checksums and what each needs | to build |
| WEB-03 | Privacy notice and terms — carries the PLAT-05 consent notice and grievance officer | to build |
| WEB-04 | Help and how-to-use, per role | to build |
| WEB-05 | Route split: the app moves off `/` so the landing page can own it | to build |

### 3.3 Citizen — C

| ID | Feature | State |
|---|---|---|
| C-01 | Ask in plain language or by voice; answer with openable citations | built |
| C-02 | Upload redaction before analysis | to build |
| C-03 | Notice and summons explainer: what it demands, the deadline, the risk | to build |
| C-04 | Rights explainer — arrest, stop, summons; offline and printable | to build |
| C-05 | Forum and limitation router: where to go, by when, what it costs | to build ⚠ |
| C-06 | Drafting beyond FIR facts: complaint, RTI, consumer complaint, legal notice | to build |
| C-07 | Multilingual | to build |
| C-08 | Guided journeys for the situations people actually arrive with | to build |
| C-09 | Legal aid referral — eligibility and the DLSA to approach | to build |
| C-10 | My matter: deadlines and reminders for their own situation | to build |

Built today beyond C-01: emergency and refusal screening · abstention on corpus
gaps · per-section grounding under each answer · source inspector · document
upload and analysis · session history · follow-up routing.

⚠ **C-05 carries real liability.** A wrong limitation period loses a case. It
must cite the limitation provision, show its basis, and abstain rather than
guess. See [06-PLAN](06-PLAN.md) §3 — this needs a decision before it is built.

### 3.4 Police — P

| ID | Feature | State |
|---|---|---|
| P-01 | Case register with proven isolation; evidence upload | built |
| P-02 | FIR fact extraction and drafting | built |
| P-03 | Statutory investigation timeline — nine BNSS deadlines, persisted | built |
| P-04 | BNSS compliance record — 24 requirements plus four conditional | built |
| P-05 | Deadline **register**: due, overdue, breached, across cases | to build |
| P-06 | Compliance as a record: date and evidence attached per duty | to build |
| P-07 | Drafting set: s.35(3) notice, s.94 production order, seizure memo, case diary, remand application, chargesheet skeleton on s.193(3) heads | to build |
| P-08 | Offence ingredient checklist — does the evidence establish each element | to build |
| P-09 | Search and seizure legality check (s.103/105) | to build |
| P-10 | Evidence inventory, chain of custody, witness tracker | to build |
| P-11 | Supervisory view: unit-wide compliance and imminent breaches | to build |
| P-12 | Court-ready case file export | to build |

Not built and not planned: anything beyond the BNSS. No state police manual
coverage, no court-stage tracking.

### 3.5 Advocate — A

| ID | Feature | State |
|---|---|---|
| A-01 | Case corpus, defence strategy with adverse arguments, authority mapping, four specialist personas | built |
| A-02 | Bail: regular, anticipatory, default, s.479 undertrial release | to build |
| A-03 | Drafting library with authorities inserted from retrieval | to build |
| A-04 | Matter calendar: limitation and hearing dates | to build |
| A-05 | Brief and synopsis generation | to build |
| A-06 | Precedent research by court, year and holding | **blocked** on CORP-01 |
| A-07 | Is this still good law — judgment citator | **blocked** on CORP-03 |
| A-08 | Check the opponent's cited authorities | **blocked** on CORP-01 |
| A-09 | Case comparison on facts | **blocked** on CORP-01 |
| A-10 | The debate room | parked — ~25 sequential model calls, 12–16 minutes |

A-06 to A-09 must not be started before the judgment corpus exists. Against 93
judgments they would appear to work and would be wrong.

### 3.6 Admin — AD

| ID | Feature | State |
|---|---|---|
| AD-01 | User management, corpus intake, statistics, audit log | built |
| AD-02 | Release console: run the gates, read results, approve or refuse a cutover, roll back | to build |
| AD-03 | Corpus coverage browser; currency flags; OCR and verification queues as work lists | to build |
| AD-04 | Answer-quality dashboard: abstention, citation coverage, unsupported claims, latency, over time | to build |
| AD-05 | Feedback triage and incident handling: trace a bad answer to its chunks, quarantine a document | to build |
| AD-06 | Full user management: suspend, force reset, role change, MFA enforcement | to build |
| AD-07 | Data retention and deletion honoured end to end | to build |
| AD-08 | Model and prompt configuration with A/B comparison | to build |

Admin deliberately **cannot** reach private case material through a general
search, and that stays true.

### 3.7 Corpus — CORP

| ID | Feature | State |
|---|---|---|
| CORP-01 | Judgments at volume: Supreme Court and every High Court served | to acquire |
| CORP-02 | State law for every state claimed | to acquire |
| CORP-03 | Overruling and subsequent-history data | to acquire |
| CORP-04 | Incremental ingestion — add, replace, retire without a rebuild | built |
| CORP-05 | Amendment and notification watch | built |
| CORP-06 | "The law you relied on changed" — notify recipients of a superseded citation | built |
| CORP-07 | Golden set v4: document identities instead of phrase predicates | to build |
| CORP-08 | Proactive expert review on sampled answers | built |

### 3.8 Per-role answer shape

The same five verified categories are named for what each role reads for. An
officer reading "practical next steps" reads advice; the BNSS imposes
obligations, so the police heading is "Required procedural steps". An advocate
needs the contrary case flagged as such, not filed under uncertainties.

| category | citizen | police | advocate |
|---|---|---|---|
| legal_basis | Why this is the legal position | Governing provision and legal basis | Authority and legal basis |
| application | How this applies to you | Application to this matter | Application to these facts |
| next_step | What you can do now | Required procedural steps | Steps available |
| limit | Important limits | Safeguards, limits and uncertainties | Contrary considerations, limits and gaps |

These headings are an interface, not decoration.
`frontend/lib/answer-presentation.ts` sorts an answer into basis, limits, footer
and body by matching them. Both sides pin the same fifteen strings, and a
rename fails on both.

---

## 4. What we will not build

- **Outcome prediction** ("will I win") — unverifiable, and harmful in a legal
  tool
- **E-filing and court-portal integration** — brittle, high maintenance, no
  corpus advantage. Read-only case-status lookup is the one defensible
  exception.
- **Lawyer marketplace, social features, gamification** — a different product
- **Anything that paraphrases the law in translation.** Explain in any
  language; quote the authority in its own words.
