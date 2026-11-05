# 01 — Product

*What Corpusil is, where it stands, and every feature with its state.
Updated 5 November 2026. Performance figures in 2.1 predate the v6 corpus.*

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
| Backend tests | **2,785** plus 37 red team, passing on the isolated stack, 5 November 2026 |
| Frontend tests | 334 unit, 149 browser (Playwright, mocked backend) |
| API endpoints | 58 across 16 routers |
| Corpus | 1,596 rows / **1,593 unique documents** / 56,290 pages / 86,127 passages |
| Judgments | **93** (79 Supreme Court, 14 AP High Court) |
| Jurisdictions | 1,290 Central · 285 Andhra Pradesh · 18 Telangana |
| Source URLs missing | 0 · not verified official: 0 · OCR outstanding: 0 |
| Serving | `global_legal_corpus_v6` |
| Release gates | 7 in one command, plus a volume-vs-ranking analysis |
| Desktop | Tauri, three targets, signed updater |
| Public website | landing, install, privacy, terms and help pages |

### 2.1 Measured performance

On v6, 5 November 2026, on an M-series host with the 14B model:

| | Fast | Deep |
|---|---|---|
| p50 | **0.55 s** | 47.9 s |
| p95 | 1.17 s | 59.1 s |
| First useful output, p95 | as above | 7.1 s |

Fast takes longer than it did because it now reads the top Acts closely. That took the
governing section shown from 39 to 67 of 94 questions, which was worth the half second.

| Golden set v4, on v6 | |
|---|---|
| Governing section shown, Fast | 67 of 94 |
| Should-refuse questions refused | 8 of 8 |
| Currency correct, Deep | 1.000 |
| Abstention correct, Deep | 0.931 |
| Ground coverage, Deep | 0.540 |
| Unsupported published claims | 0 |

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
| PLAT-04 | Account recovery: email verification, password reset, MFA for professionals, device list | built |
| PLAT-05 | DPDP compliance: consent, data-principal rights, retention, erasure, grievance officer | built |
| PLAT-06 | Export and print an answer with its citations intact | built |
| PLAT-07 | Searchable history: find, pin, rename, organise by matter | built |
| PLAT-08 | Deep progress over SSE instead of polling | built |
| PLAT-09 | Human fallback on abstention — route to legal aid or a panel advocate | built |
| PLAT-10 | Offline desktop with a local corpus pack | partial |
| PLAT-11 | Accessibility and low bandwidth | built |
| PLAT-12 | Information-not-advice framing; Bar Council constraints respected | built |

| PLAT-13 | Open a provision by citation, with its old or new counterpart, and browse an Act | built |
| PLAT-14 | Refuse foreign-law and non-legal questions at once | built |
| PLAT-15 | Machine translation of verified answers, withheld if a number or source changed | built |

### 3.2 Website — WEB

The product has no public face, and nowhere to publish the privacy notice DPDP
requires. That makes this a compliance dependency, not only marketing. The
frontend is already a static export, so the pages themselves are cheap.

| ID | Feature | State |
|---|---|---|
| WEB-01 | Landing page: what it is, who it is for, the trust story — shown instead of a login box | built |
| WEB-02 | Install page: macOS, Windows and Linux builds, with checksums and what each needs | built |
| WEB-03 | Privacy notice and terms — carries the PLAT-05 consent notice and grievance officer | built |
| WEB-04 | Help and how-to-use, per role | built |
| WEB-05 | Route split: the app moves off `/` so the landing page can own it | built |

### 3.3 Citizen — C

| ID | Feature | State |
|---|---|---|
| C-01 | Ask in plain language or by voice; answer with openable citations | built |
| C-02 | Upload redaction before analysis | built |
| C-03 | Notice and summons explainer: what it demands, the deadline, the risk | built |
| C-04 | Rights explainer — arrest, stop, summons; offline and printable | built |
| C-05 | Forum and limitation router: where to go, by when, what it costs | built ⚠ |
| C-06 | Drafting beyond FIR facts: complaint, RTI, consumer complaint, legal notice | built |
| C-07 | Multilingual | built |
| C-08 | Guided journeys for the situations people actually arrive with | built |
| C-09 | Legal aid referral — eligibility and the DLSA to approach | built |
| C-10 | My matter: deadlines and reminders for their own situation | built |

Also built beyond C-01: emergency and refusal screening · abstention on corpus
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
| P-05 | Deadline **register**: due, overdue, breached, across cases | built |
| P-06 | Compliance as a record: date and evidence attached per duty | built |
| P-07 | Drafting set: s.35(3) notice, s.94 production order, seizure memo, case diary, remand application, chargesheet skeleton on s.193(3) heads | built |
| P-08 | Offence ingredient checklist — does the evidence establish each element | built |
| P-09 | Search and seizure legality check (s.103/105) | built |
| P-10 | Evidence inventory, chain of custody, witness tracker | built |
| P-11 | Supervisory view: unit-wide compliance and imminent breaches | built |
| P-12 | Court-ready case file export | built |

Not planned: state police manual coverage and court-stage tracking.

### 3.5 Advocate — A

| ID | Feature | State |
|---|---|---|
| A-01 | Case corpus, defence strategy with adverse arguments, authority mapping, four specialist personas | built |
| A-02 | Bail: regular, anticipatory, default, s.479 undertrial release | built |
| A-03 | Drafting library with authorities inserted from retrieval | built |
| A-04 | Matter calendar: limitation and hearing dates | built |
| A-05 | Brief and synopsis generation | built |
| A-06 | Precedent research by court, year and holding | built, over the judgments held, and says how few |
| A-07 | Is this still good law — judgment citator | built, partial: no overruling data (CORP-03) |
| A-08 | Check the opponent's cited authorities | built, over the judgments held, and says how few |
| A-09 | Case comparison on facts | built, over the judgments held, and says how few |
| A-10 | The debate room | built, and slow: about 25 model calls |

A-06 to A-09 state the number of judgments searched in every result. Against the
93 held that is a small set, and an absence from it proves nothing.

### 3.6 Admin — AD

| ID | Feature | State |
|---|---|---|
| AD-01 | User management, corpus intake, statistics, audit log | built |
| AD-02 | Release console: run the gates, read results, approve or refuse a cutover, roll back | built |
| AD-03 | Corpus coverage browser; currency flags; OCR and verification queues as work lists | built |
| AD-04 | Answer-quality dashboard: abstention, citation coverage, unsupported claims, latency, over time | built |
| AD-05 | Feedback triage and incident handling: trace a bad answer to its chunks, quarantine a document | built |
| AD-06 | Full user management: suspend, force reset, role change, MFA enforcement | built |
| AD-07 | Data retention and deletion honoured end to end | built |
| AD-08 | Model and prompt configuration with A/B comparison | built |

Admin deliberately **cannot** reach private case material through a general
search, and that stays true.

Police and advocates also have: a case timeline read from the files · who's who and possible contradictions, each quoted from the files · many files at once · private case notes · Word export.

### 3.7 Corpus — CORP

| ID | Feature | State |
|---|---|---|
| CORP-01 | Judgments at volume: Supreme Court and every High Court served | to acquire |
| CORP-02 | State law for every state claimed | to acquire |
| CORP-03 | Overruling and subsequent-history data | to acquire |
| CORP-04 | Incremental ingestion — add, replace, retire without a rebuild | built |
| CORP-05 | Amendment and notification watch | built |
| CORP-06 | "The law you relied on changed" — notify recipients of a superseded citation | built |
| CORP-07 | Golden set v4: document identities instead of phrase predicates | built |
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
