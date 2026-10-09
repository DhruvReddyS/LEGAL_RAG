# Implementation plan, from the end of the v5 build

*Written 9 October 2026, with `global_legal_corpus_v5` at 799 of 1,563 documents.*

This is the execution sequence. It does not restate the product promise or the
release gates — those are in [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md), and
nothing here weakens them. What follows is the order the work happens in, why
that order, and what has to be true before each phase is called done.

Three principles decide the ordering, and they are worth stating because they
contradict the instinct to build features first.

1. **The corpus is the ceiling.** Half the advocate lane cannot work on 93
   judgments, and no feature compensates. Breadth and freshness outrank
   features.
2. **The trust layer is the product.** Grounded citations, openable sources,
   repeal labelling and honest abstention are what distinguish this from a
   chatbot. No feature may bypass them, and any feature that would is cut.
3. **Law decays.** A legal product that does not update is wrong within
   months, silently. Keeping the corpus current is a feature, not maintenance.

Lanes follow the existing split: **Codex** owns corpus acquisition, metadata,
source verification, documentation and release evidence; **Claude** owns
backend, retrieval, answer quality and the application. Phases name the lane
where it is not obvious.

---

## Phase 0 — Close out v5

Begins the moment the keeper reports the build finished. Everything here is
already built; this phase runs it.

1. Confirm the worker and keeper have exited, and that nothing else is
   running. Every gate is a measurement and a busy host invalidates it.
2. Run `scripts/run_corpus_gates.sh global_legal_corpus_v5 v5-cutover`.
   Seven gates plus the haystack analysis.
3. **Analyse failures, separating volume from ranking.** v5 is roughly twice
   v4's size, so recall and citation numbers move on volume alone.
   `golden_set_haystack_report.py` reports which golden-set items got an
   easier haystack; only the rest support a claim about retrieval.
   Do **not** `--record` a baseline over a failing gate.
4. Close the known v5 payload gaps:
   - `ocr_required` absent from early points, `currency_note` empty for early
     documents — `backfill_manifest_payload.py` (Codex), payload-only
   - 129 citation-furniture chunks and 36 doubled-text chunks —
     `prune_reclassified_noise.py`, after reviewing all 129
   - Re-extract the 3 doubled-text-layer documents (Child Helpline SOP,
     victim care scheme, NALSA mediation SOP)
5. Re-run the gates. Cutover only on a clean pass, reviewed by Codex.
6. Measure the true tokenised maximum chunk length and set `max_length` from
   data for the next build. It is 8,192 today; the longest real chunk is
   64,802 characters.

**Done when:** all seven gates pass on v5, v5 serves, v4 is retained for
rollback, and the evidence is written under `docs/evidence/gates/v5-cutover`.

---

## Phase 1 — Keep the law current

The highest-value work after cutover, because without it everything decays and
nobody notices. It also removes the full-rebuild cost that currently makes
every corpus change a day-long operation.

1. **Incremental ingestion.** Add, replace and retire a document without
   rebuilding the collection. The per-document ledger already supports resume;
   this makes it a first-class operation with its own gate.
2. **Amendment and notification watch** (Codex). Scheduled acquisition from
   the official gazette sources already in the manifest, landing as intake
   candidates rather than silent writes.
3. **"The law you relied on changed."** When a provision cited in a delivered
   answer is later amended or repealed, tell the user who received it. The
   currency engine already detects the condition; this connects it to the
   people it affects.
4. **Golden set v4.** Replace phrase predicates with document identities. The
   current set is 61 items matching `{"contains": "..."}`, which is why
   recall@5 once read 0.927 while the governing provision was absent from the
   top 100. Until this is fixed, every retrieval number is softer than it
   looks.
5. **Proactive expert review.** Sampled answers reviewed on a schedule by a
   lawyer, with corrections feeding the golden set. Feedback triage only
   surfaces what a user bothered to flag.

**Done when:** a new amendment can reach users without a full rebuild, a
superseded citation notifies its recipients, and the golden set asserts
document identity.

---

## Phase 2 — Corpus breadth (Codex lane)

Acquisition, not engineering, and the hard ceiling on the advocate lane.

| Gap | Today | Needed |
|---|---|---|
| Judgments | 93 (79 SC, 14 AP HC) | Thousands; SC plus every High Court served |
| States | Central, AP, a little Telangana | Every state the product claims to serve |

1. Judgment acquisition at volume, with neutral citation, court, bench, date
   and outcome as first-class metadata.
2. State law for each state claimed — tenancy, land, police rules, welfare.
3. **Licensing review before acquisition, not after.** Judgment text and
   commercial headnotes have different terms.
4. Overruling and subsequent-history data, if a citator is to be built. Absent
   this, the citator is not possible and should not be promised.

**Done when:** coverage per claimed jurisdiction is measured and published,
and the advocate features in Phase 4 have the material they need.

---

## Phase 3 — Platform foundations

Nothing role-specific ships before these. Two of them are legal obligations,
not features.

1. **Account recovery** — email verification, password reset, MFA for police
   and advocates, device/session list with sign-out-everywhere.
2. **DPDP Act 2023 compliance** — consent notices, purpose limitation,
   data-principal rights (access, correction, erasure), retention schedule,
   grievance officer, breach notification. Citizens upload FIRs and police
   upload case material; this is mandatory.
3. **Information, not advice** — consistent framing throughout, and Bar
   Council constraints respected on anything advocate-facing.
4. **Export and print** an answer with its citations intact.
5. **Searchable history** — find, pin, rename, organise by matter.
6. **Deep progress over SSE.** The backend already emits the events; the
   frontend polls.
7. **Human fallback on abstention.** When the system refuses — which it
   should, often — route to legal aid or a panel advocate. Abstention with a
   next step reads as honesty; without one it reads as failure.

**Done when:** an account can be recovered, a citizen can exercise their data
rights end to end, and no answer is a dead end.

---

## Phase 4 — Role features

Ordered by dependency and by how much is already built.

### 4a. Admin release console — first
Until this exists, releasing is a terminal command one person can run. It
unblocks everyone else.

- Run the gates from the UI, read results, approve or refuse a cutover, roll
  back
- Corpus coverage browser; currency-flagged instruments; OCR and
  source-verification queues as work lists
- Answer-quality dashboard: abstention rate, citation coverage, unsupported
  claims, latency, by role, over time — all measured today, none visible
- Feedback triage, and incident handling that traces a bad answer to its
  chunks and quarantines the document
- User management and an exportable audit trail

### 4b. Police — most value for least new code
The deadline logic is the best-engineered part of this lane and never leaves
the function that computes it.

- Deadline register: persist and surface the BNSS clocks (24-hour production,
  s.187(3) 60/90 days, s.193(2) two months); due, overdue, breached
- Compliance checklist as a record: date and evidence per duty
- Drafting beyond the FIR, which is the only kind today: s.35(3) notice,
  s.94 production order, seizure memo, case-diary entry, remand application,
  chargesheet skeleton on s.193(3)'s own heads
- Offence ingredient checklist
- Search and seizure legality check (s.103/105)
- Evidence inventory, chain of custody, witness tracker
- Supervisory view; court-ready case-file export

### 4c. Citizen
- Notice and summons explainer, extending document extract
- Legal aid referral — 44 NALSA and legal-services documents are already in
  the corpus and unused for this
- Rights card: offline and printable, from BNSS s.35, s.47 and Article 22
- Guided journeys for the situations people actually arrive with
- Forms filled from what the user already said
- **Forum and limitation period.** Deliberately last in this group: a wrong
  limitation number loses a case. Requires an explicit decision on how
  conservative to be, must cite the limitation provision, and must abstain
  rather than guess.

### 4d. Advocate
- Bail: regular, anticipatory, default, and s.479 undertrial release. The
  largest single gap in the product.
- Drafting library with authorities inserted from retrieval
- Matter calendar, reusing the police deadline engine
- Brief and synopsis generation
- **Blocked on Phase 2:** precedent research, "is this still good law",
  checking the opponent's authorities, case comparison. Do not start these
  before the judgment corpus exists.

---

## Phase 5 — Reach

Deliberately last, by decision: features first, then the multiplier.

1. **Multilingual** — Hindi and the major regional languages. The *answer* is
   translated; the law is quoted in its original text and never paraphrased in
   translation.
2. **Voice in and out.** Not a convenience in India — it is what makes the
   citizen product reachable at all for low-literacy users.
3. **Offline desktop** with a local corpus pack: rural users, and police
   stations with poor connectivity.
4. **Accessibility and low bandwidth.**

---

## Decisions needed from the product owner

These are not engineering calls and the work should not start without them.

| Decision | Why it is yours |
|---|---|
| How conservative limitation guidance should be | A wrong number loses a case |
| Whether to acquire judgment and overruling data | Decides whether the citator exists at all |
| Which states the product claims to serve | Decides the acquisition scope |
| Whether any query may leave the device | Hosted-model trial is a privacy policy decision before an engineering one |

---

## What is deliberately excluded

- Outcome prediction — unverifiable, and harmful in a legal tool
- E-filing and court-portal integration — brittle, no corpus advantage.
  Read-only case-status lookup is the one defensible exception.
- Lawyer marketplace, social features, gamification
- Any feature that paraphrases the law in translation
