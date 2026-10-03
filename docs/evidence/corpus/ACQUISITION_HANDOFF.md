# Acquisition handoff

Two agents acquire documents into this corpus in parallel. This file is how
they stay out of each other's way. Read it before starting a batch; the agent
that finishes a batch updates it in the same commit.

Last updated: 2026-10-03, after 970 canonical documents.

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
5. **Decline optional cookies** on these CMS sites. The banner suppresses the
   document list entirely: on legislative.gov.in it turned 0 visible documents
   into 114.

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
