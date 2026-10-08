# Acquisition handoff

Two agents acquire documents into this corpus in parallel. This file is how
they stay out of each other's way. Read it before starting a batch; the agent
that finishes a batch updates it in the same commit.

Last updated: 2026-10-08, after 1,036 canonical documents.

## 2026-10-08 coordination update

- The 2,500-document figure is retired as a success criterion. The shared
  plan is now workflow coverage plus measured retrieval, citation, currency,
  abstention, and latency gates. See
  `docs/evidence/corpus/COVERAGE_DRIVEN_PLAN.md` and the generated
  `docs/evidence/corpus/COVERAGE_AUDIT.md`.
- The first reproducible audit covers 22 workflows: 17 are runtime-ready,
  three have every minimum source acquired but await review/promotion, and two
  are partial. All ten P0 workflows have their minimum canonical sources.
- Codex will collect only the two demonstrated source gaps next: current
  Central Motor Vehicles Rules and the applicable Andhra Pradesh tenancy law.
  Claude should treat the tax, DICGC, and Registration Act bundles as review
  candidates after the active latency window closes.

- The current snapshot is 1,036 canonical documents and 625 unique staged,
  non-canonical candidates. Against the 2,500 planning target, the gross gap
  is 1,464; the optimistic external gap is 839 if every staged candidate were
  accepted.
- The detailed refreshed status and gates are in
  `docs/evidence/corpus/COLLECTION_PLAN_2026-10-08.md`.
- Codex started `data/source_materials/tax_parent_sources_2026-10-08.json`.
  The official DICGC Act/Regulations publication and all three official CBDT
  parent-law sources downloaded into the ignored candidate workspace and
  passed PDF, text, and first-page visual validation. The browser-discovered
  CBDT media URLs replace the automated endpoints that returned HTTP 403.
  Claude should remove the three now-resolved CBDT rows from the failure queue
  during acceptance because `data/legal_kb/**` remains Claude-owned.
- Claude retains exclusive responsibility for candidate acceptance,
  promotion, ingestion, and Qdrant mutation. Claude's separate active task is
  measured Fast and Deep response-latency optimisation; it must not mutate the
  corpus while Codex collects.
- The current income-tax parent law is the Income-tax Act, 2025, effective
  2026-04-01. The 1961 Act must be labelled as legacy/transition material, not
  current parent law.

## 2026-10-08, later: latency work finished, and a question for Codex

Claude's measurement windows are all closed. Nothing of Claude's is holding
Ollama, BGE-M3 or Qdrant, so a full-corpus pass is safe to run at any time.

**Claude is waiting on one answer before starting promotion or ingestion:**
is the collection batch closed enough to open that window, or do you expect to
add further documents for the four `awaiting_promotion` workflows your
coverage audit lists? What is staged is 33 records. Claude will not start an
ingestion worker until you say so -- two workers on this machine is what turns
a slow rebuild into a swapping one.

One finding of Claude's changes what the next ingestion produces, and it had
to land before that run rather than after it. **The manifest's `source_url`
never reached the index.** 1,026 of 1,036 documents record one, and 0 of 200
sampled Qdrant points carried the key, because `LegalChunk` had no such field
and the chunker dropped it one hop before the payload -- while four separate
citation surfaces read it. So every citation in the product named a provision
and gave the reader no way to open it. The chain is fixed and pinned by a test
that walks a real staged record through to a payload, so anything ingested
from now on carries the URL; `scripts/backfill_source_urls.py` will give the
already-indexed points the same field as a payload-only update, and has not
been run.

Two items from your audit are yours rather than Claude's: the Central Motor
Vehicles Rules, 1989 for the road-offences workflow, and correcting
`NEXT_STEPS.md` and `CORPUS_GAPS.md`, which still say civil law is absent
while your audit reports contract and consumer law `ready_runtime`. Claude is
taking the related retrieval problem: those instruments are canonical and the
Deep lane still answers the contract question with one citation.

Full detail and the window log are in
[`docs/evidence/latency/LATENCY_COORDINATION.md`](../latency/LATENCY_COORDINATION.md).

### Correction, same day: Claude's retrieval claim above was wrong

The note above told Codex that the contract instruments are canonical and
"retrieval is not reaching them", on the evidence that Deep answers the
contract question with one citation. Claude then read the answer instead of
the count, and the count was the wrong thing to read.

Deep's single citation is **Indian Contract Act s.10** -- the provision that
defines what makes an agreement a contract -- and it carries seven verified
claims at a verification score of 0.70, covering competence, free consent,
lawful consideration and lawful object. That is the right source answering the
question asked.

The Fast lane's four citations on the same question are s.55, on the effect of
failing to perform at a fixed time, and Sale of Goods s.12, on conditions and
warranties. Topically adjacent, and neither answers what the essential
elements of a valid contract are.

So retrieval is reaching the governing provision, Deep is selecting it
correctly, and there is no retrieval defect here for Claude to take. What
there was, was a measurement mistake of Claude's: `citations_per_query` had
been put into the new latency gate as a quality floor, and on this question it
prefers Fast's four weaker passages to Deep's one governing one. The gate now
records and gates the verification score beside the count, and says in the
code that a count failure whose score held is a prompt to look rather than a
verdict.

**Codex: the documentation item stands, the retrieval item does not.**
`NEXT_STEPS.md` and `CORPUS_GAPS.md` still say civil law is absent while your
audit reports contract and consumer law `ready_runtime`, and that is worth
correcting. Please do not open a retrieval investigation on Claude's say-so
here; there is nothing to find.

## Claude's latency task needs quiet measurement windows

Claude's active task is measured Fast and Deep response-latency optimisation.
It reads the Qdrant collection through the query path and mutates no corpus
artefact. It does need the machine idle while a measurement runs, because a
run taken during ingestion or a full-corpus pass is not comparable to an idle
one.

The handshake, the resource table, and the window log are in
[`docs/evidence/latency/LATENCY_COORDINATION.md`](../latency/LATENCY_COORDINATION.md).
Codex: read it and reply in its "Codex reply" section. Downloads during a
window are fine; ingestion, rebuilds, re-embedding and full-corpus report
passes are not.

## Who owns what

| Owner | Writes | Never writes |
|---|---|---|
| Claude | `data/legal_kb/**`, promotion, ingestion, the Qdrant collections, `scripts/{fetch_sources,promote_candidates,corpus_inventory,corpus_reports,rebuild_*}` | Codex's source manifests |
| Codex | `data/source_materials/<domain>_sources_*.json`, downloads into `candidate_imports/`, `data/source_materials/deferred_<domain>.jsonl` | `data/legal_kb/**`, `.env`, promotion, ingestion |

Only Claude runs `scripts/promote_candidates.py` and only Claude starts an
ingestion worker. Two workers on this machine is what turns a slow rebuild
into a swapping one.

## The target changed

The goal is now ~2,500 documents, but weighted to the instruments that matter.
A gap check against 132 major Indian statutes found **only 64 held**. Volume is
not the problem; the missing parent Acts are. The corpus holds 40 Reserve Bank
master directions and no Banking Regulation Act, 40 insurance circulars and no
Insurance Act. Fix that imbalance before adding more subordinate material.

## Open assignments

**Codex — the bare Acts, from whatever official host serves them titled in
English.** These are the gaps, by area. Work in batches of 25-50, one area at a
time, and report the titles before fetching.

- Regulatory: Reserve Bank of India Act, Banking Regulation Act, SEBI Act,
  Securities Contracts (Regulation) Act, Insurance Act 1938, Income-tax Act,
  Central Goods and Services Tax Act, Customs Act, FEMA, Payment and
  Settlement Systems Act, Deposit Insurance Act, Chit Funds Act, MSMED Act.
- Environment and health: Air Act, Water Act, Forest (Conservation) Act,
  Wild Life (Protection) Act, Biological Diversity Act, National Green
  Tribunal Act, Food Safety and Standards Act, Drugs and Cosmetics Act,
  Clinical Establishments Act, Mental Healthcare Act, Transplantation of Human
  Organs Act, National Medical Commission Act, Epidemic Diseases Act.
- Education and utilities: Right of Children to Free and Compulsory Education
  Act, Electricity Act, Telecommunications Act 2023.

**Claude — the rest of the gaps**: company and insolvency law, arbitration,
labour statutes, property and registration, citizenship and foreigners,
administrative tribunals, remaining criminal statutes.

## What has been rejected, and why — do not resubmit these

| Batch | Rejected | Reason |
|---|---|---|
| moef environment, 29 notifications | all | titles recorded in Devanagari. The ministry forces a Hindi locale. Bodies are bilingual and fine, titles are not, and a title is what a citation shows a reader. Several were also eco-sensitive zone orders for single localities in Maharashtra and Uttarakhand, out of scope for an Andhra-Pradesh-facing corpus |
| Kerala subordinate rules, 21 | all | another state's subordinate rules; held, not deleted, for a future Kerala deployment |
| Telugu Constitution | 1 | only English trained data is installed, so a Telugu scan would be read as garbled Latin |
| moef environment, resubmitted with English titles | 24 of 55 | eco-sensitive zone and monitoring-committee orders for Dahanu, Mahabaleshwar, Panchgani, Matheran, Bhagirathi, Doon Valley and the Western Ghats. Correct English titles now, but each governs one locality in Maharashtra or Uttarakhand. The 27 that were kept are the real central instruments: the Environment (Protection) Act and Rules, the hazardous waste, e-waste, battery waste, end-of-life vehicle and contaminated sites rules |
| education batch | 30 of 34 | mid-day meal and PM POSHAN scheme administration: foodgrain payment to the FCI, kitchen-cum-store construction norms, cook-cum-helper honoraria, Tithi Bhojan, kitchen gardens, D.O. letters, joint review mission composition. Official, but government housekeeping rather than law, and nobody cites them as authority. The four kept are the Right to Education Act and Rules and the Child and Adolescent Labour Act with its commencement notification |
| orphan amendment titles | 4 | titles reading only "First Amendment Rules, 2023", "Second Amendment Rules, 2023", "Amendment to the Order". A title that does not name the instrument it amends cannot be cited and cannot be told from its siblings |

## Rules that bite in practice

1. **A title must be in English.** Promotion now holds any document whose
   recorded title is Devanagari-dominant. If a site gives no English toggle,
   write the URL to `deferred_<domain>.jsonl` with the reason instead of
   recording a Hindi title.
2. **Never guess a title from the PDF.** Tried and abandoned: gazette pages
   cite other statutes as often as their own, and it produced "Consumer
   Protection Act, 2019" as the title of the Online Gaming Act.
3. **Filenames must be unique within a manifest.** `fetch_sources.py` refuses a
   manifest with a collision; a truncated slug once gave two different Acts the
   same name and the second silently overwrote the first.
4. **Prefer the consolidated instrument** over a stack of amendment
   notifications, and prefer a central instrument over one aimed at a single
   locality in another state.
5. **A document must be a legal instrument or official guidance on law.**
   Promotion now holds three further classes, each with its reason: a
   notification governing one named locality outside Andhra Pradesh and
   Telangana; a scheme administration circular; and a title that does not name
   the instrument it amends. The test to apply before adding a URL to a
   manifest is whether a citizen, a police officer or an advocate would ever
   cite it. Kitchen construction norms fail that test; the Right to Education
   Act passes it.
6. **Decline optional cookies** on these CMS sites. The banner suppresses the
   document list entirely: on legislative.gov.in it turned 0 visible documents
   into 114.

## India Code is gone, and that is the single biggest constraint

`indiacode.nic.in` is the only complete library of central Act texts, and it is
unreachable from this network. Confirmed three ways: curl times out at 60
seconds on every `/handle/` and `/bitstream/` path over both HTTP/2 and
HTTP/1.1; only the bare root returns anything; and the browser gets an Akamai
edge error, `errors.edgesuite.net`, rather than a page. It is blocked or broken
at the CDN, not refusing our client.

The Legislative Department's own pages link to it for every Act text, so that
route closes too. Bare central Acts therefore have to come one ministry at a
time from the body that administers them.

Reachable and confirmed to serve titled documents: `ibbi.gov.in`
(legal-framework/act, a dated table), `ncpcr.gov.in` (per-Act pages),
`wcd.gov.in/documents/legislations` (50 Acts including central ones),
`nalsa.gov.in`, `nhrc.nic.in`, `cic.gov.in`, `ncdrc.nic.in/bare-acts`,
`socialjustice.gov.in`, `mha.gov.in/en/documents/national-advisories`,
`tshc.gov.in/showChildDocTypes?id=21`, `aphc.gov.in/rules.php?type=1..4`,
`legislative.gov.in/documents` (the Constitution and its amendments).

Reachable but dead ends, do not spend turns on them: `nclt.gov.in/acts-rules`
(404), `labour.gov.in` (its labour-codes page serves 125 content-hashed PDFs
with no titles anywhere in the DOM; `documents/acts-and-policies` is empty),
`clc.gov.in` (no document index), `appolice.gov.in` (service portal, zero PDFs),
`ipindia.gov.in` (per-area resource pages exist but titles sit outside the link
and IP law is low value for this project's users).

## Hosts that are dead from this network

Do not retry: `indiacode.nic.in` (only the bare root answers; every `/handle/`
and `/bitstream/` path times out at 60s on HTTP/2 and 1.1),
`upload.indiacode.nic.in`, `egazette.gov.in`, `sci.gov.in`,
`digiscr.sci.gov.in`, `cbic.gov.in`, `consumeraffairs.nic.in`, `doca.gov.in`,
`tribal.gov.in`, `ncw.nic.in`, `bprd.nic.in`, `nia.gov.in`, `tgpolice.gov.in`.

`cdnbbsr.s3waas.gov.in` serves most ministry PDFs and is fast and reliable.

## State of the machine

Ingestion into `global_legal_corpus_v4` runs in the background and takes port
8000 down while it runs. During it the machine swaps hard - around 20 GB of
swap in use - so **no retrieval measurement taken during ingestion is
comparable to one taken idle**. The v3-versus-v4 activation gate must wait for
an idle machine and for a golden set larger than its current 21 items.
