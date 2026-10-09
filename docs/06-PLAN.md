# 06 — Plan

*What we build next, in what order, and who owns it. Written 9 October 2026
with the v5 corpus build at 801 of 1,563 documents.*

Features are identified by the catalogue in [01-PRODUCT](01-PRODUCT.md) §3.
Work refers to `P-05` or `WEB-02`, not to a paraphrase.

---

## 1. What outranks features

Three things decide whether this product is good, and none of them is a
feature. They are stated first because each is easy to leave off a plan.

### 1.1 The corpus is the ceiling

93 judgments cannot support precedent research, a citator, case comparison or
checking an opponent's authorities — A-06 to A-09, all blocked. Coverage is
Central law plus Andhra Pradesh, so a citizen in any other state gets nothing
state-specific on tenancy, land, police rules or welfare.

This is acquisition work, which is why it is easy to leave off a feature list.
It decides whether half the features work at all.

### 1.2 Law decays, and nothing here keeps it current

There is no pipeline for amendments, notifications or new judgments; ingestion
is a manual full rebuild. A legal product that does not update is **wrong
within months, silently**. Keeping the corpus current is a feature — CORP-04 to
CORP-06 — not maintenance.

### 1.3 Compliance is an obligation, not a feature

Under the DPDP Act 2023, consent notices, purpose limitation, data-principal
rights, a retention schedule, a grievance officer and breach notification are
mandatory. Citizens upload FIRs and police upload case material. None of it
exists, and the privacy notice has nowhere to live because there is no public
website — which is why PLAT-05 and WEB-03 are built together.

### 1.4 And the thing to protect

The trust layer is already the strongest asset and is genuinely ahead of what
most legal AI ships. Every feature below is built so that it never undermines
it. A feature that would bypass grounding, currency labelling or abstention is
cut rather than weakened.

---

## 2. The phases

Lanes follow the established split. **Codex** owns corpus acquisition,
metadata, source verification, documentation and release evidence. **Claude**
owns backend, retrieval, answer quality and the application.

The ordering deliberately contradicts the instinct to build features first:
building the advocate lane against 93 judgments would waste months.

### Phase 0 — Close out v5

Triggers the moment the build finishes. Everything here already exists; this
phase runs it.

1. Confirm the worker and keeper have exited and the host is idle. Every gate
   is a measurement, and a busy host invalidates it.
2. `scripts/run_corpus_gates.sh global_legal_corpus_v5 v5-cutover`
3. **Analyse failures separating volume from ranking.** v5 is roughly twice
   v4's size, so recall and citation numbers move on volume alone.
   `scripts/golden_set_haystack_report.py` reports which golden-set items got
   an easier haystack; only the rest support a claim about retrieval.
   **Never `--record` a baseline over a failing gate.**
4. Close the known payload gaps: `ocr_required` and `currency_note` backfill
   for early points; prune the 129 citation-furniture and 36 doubled-text
   chunks after reviewing all 129; re-extract the three doubled-text documents
   (Child Helpline SOP, victim care scheme, NALSA mediation SOP).
5. Re-run the gates. Cut over only on a clean pass, reviewed by Codex.
6. Set `max_length` from measured data — 8,192 today, longest real chunk
   64,802 characters.

**Done when:** seven gates pass on v5, v5 serves, v4 is retained for rollback,
and the evidence is written under `evidence/gates/v5-cutover`.

### Phase 1 — Keep the law current
CORP-04 · CORP-05 · CORP-06 · CORP-07 · CORP-08

Highest value after cutover, because without it everything decays and nobody
notices. Incremental ingestion also removes the full-rebuild cost that makes
every corpus change a day-long operation.

CORP-07 matters more than it looks: recall@5 once read 0.927 while the
governing provision was absent from the top 100, because the golden set matches
phrases rather than documents. Until that is fixed, every retrieval number is
softer than it appears.

**Done when:** a new amendment can reach users without a full rebuild, a
superseded citation notifies the people who received it, and the golden set
asserts document identity.

### Phase 2 — Corpus breadth *(Codex)*
CORP-01 · CORP-02 · CORP-03

Acquisition, not engineering. **Licensing review happens before acquisition,
not after** — judgment text and commercial headnotes have different terms.
Without CORP-03 the citator is not possible and must not be promised.

**Done when:** coverage per claimed jurisdiction is measured and published, and
A-06 to A-09 have the material they need.

### Phase 3 — Foundations and the public face
PLAT-04 · PLAT-05 · PLAT-06 · PLAT-07 · PLAT-08 · PLAT-09 · PLAT-12 ·
WEB-01 · WEB-02 · WEB-03 · WEB-04 · WEB-05

Nothing role-specific ships before these. PLAT-05 and WEB-03 are coupled: the
consent notice has to be published somewhere, and that somewhere is the
website. WEB-05 is a routing change — the app moves off `/` so the landing page
can own it. The frontend is already a static export, so the pages are cheap,
and the install page links the artifacts the release workflow already builds
for three desktop targets.

**Done when:** an account can be recovered, a citizen can exercise their data
rights end to end, no answer is a dead end, and there is a public site that
explains the product and offers the download.

### Phase 4 — Role features

**4a. Admin** — AD-02 first. Until it exists, releasing is a terminal command
one person can run, and that person is a bottleneck on their own product. Then
AD-03, AD-04, AD-05, AD-06, AD-07, AD-08.

**4b. Police** — most value for least new code, because the deadline engine is
already the best-engineered thing in the product and never leaves the function
that computes it. P-05, P-06, P-07, P-08, P-09, P-10, P-11, P-12.

**4c. Citizen** — C-03, C-09, C-04, C-08, C-06, C-02, C-10, then **C-05 last**
in this group, by its risk.

**4d. Advocate** — A-02, A-03, A-04, A-05. **A-06 to A-09 do not start before
Phase 2 delivers.**

### Phase 5 — Reach
C-07 · PLAT-10 · PLAT-11 · voice out

Last by decision: features first, then the multiplier. The answer is
translated; the law is quoted in its original text and never paraphrased in
translation.

---

## 3. Decisions that are the owner's, not engineering's

Work on these does not start before the decision is made.

| Decision | Why it is yours | Blocks |
|---|---|---|
| How conservative limitation guidance must be | A wrong number loses a case | C-05 |
| Whether to acquire judgment and overruling data | Decides whether the citator exists at all | CORP-01, CORP-03, A-06…A-09 |
| Which states the product claims to serve | Decides the acquisition scope | CORP-02 |
| Whether any query may leave the device | A hosted model is a privacy policy decision before an engineering one | hosted-model trial |

---

## 4. How we work

1. **Gates before claims.** A milestone is complete when its measurements
   pass, not when its code exists. The gates are in
   [03-EVIDENCE](03-EVIDENCE.md) §1.
2. **Never record over a failure.** A baseline is set deliberately, never to
   make a red gate green.
3. **Measure before optimising.** Deep latency looked like an orchestration
   problem and was 97% model time. The benchmark came first and saved weeks of
   work on the wrong thing.
4. **A regression gets a test, not just a fix.** Every defect in
   [03-EVIDENCE](03-EVIDENCE.md) §2 that is closed leaves a test behind.
5. **Lanes stay separate.** Two agents do not write the same files. Corpus,
   metadata and evidence are Codex's; backend, retrieval and application are
   Claude's.
