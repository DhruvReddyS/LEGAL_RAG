# Corpus gaps — for your decision

Phase 1.7 began as the gap analysis below. On 10 September 2026, five clean
official documents were published to the extended tier. The historical
analysis is retained because it explains why the additions were chosen.

## Live expansion status — 10 September 2026

The live `global_legal_corpus_v3` collection now contains **25,323 points**:
24,810 curated Gold points plus 513 structured extended-tier points.

| area | official sources added | sections | chunks | live result |
|---|---|---:|---:|---|
| contract | Indian Contract Act, 1872; Specific Relief Act, 1963 | 228 | 446 | Contract Act s.10 ranks first for valid-contract questions |
| noise | Noise Pollution (Regulation and Control) Rules, 2000 | 8 | 12 | Rules 8, 7 and 5 rank first for night-noise questions |
| POSH | POSH Act, 2013; POSH Rules, 2013 | 41 | 55 | Act s.9 and Rules 6/7 rank first for complaint questions |

Measured citizen fast-mode results after the deployment fix (query embedding
cache cold):

| question | confidence | API time | result |
|---|---:|---:|---|
| workplace complaint and deadline | 0.85 | 542 ms | strong, POSH s.9 first |
| loudspeaker noise at night | 0.80 | 525 ms | strong, Noise Rules s.8 first |
| rental security deposit | 0.00 | 525 ms | correctly abstains; tenancy remains absent |

The Docker backend had also been querying the legacy `global_legal_corpus`
because Compose did not pass `QDRANT_GLOBAL_COLLECTION`. It now uses the v3
collection from `.env`; adding documents without this fix would not have made
the optimized corpus live.

## Next additions

1. **Consumer bundle:** Consumer Protection Act, 2019; Consumer Protection
   (Consumer Disputes Redressal Commissions) Rules, 2020; E-Commerce Rules,
   2020; Direct Selling Rules, 2021; jurisdiction and mediation rules; CCPA
   misleading-advertisement and dark-pattern guidelines.
2. **Andhra Pradesh tenancy bundle:** the current AP rent-control/tenancy
   legislation and amendments, Transfer of Property Act ss.105–117, current AP
   rules, official filing/authority guidance, and selected AP High Court cases.
   State must be known before giving a tenancy answer.
3. **Complete noise bundle:** Environment (Protection) Act, 1986, current noise
   amendments, CPCB guidance, AP Pollution Control Board complaint routes, and
   municipal/police enforcement guidance.
4. **Question-driven judgments:** add current Supreme Court and relevant High
   Court decisions only for questions where bare legislation does not resolve
   the interpretation. Do not bulk-add judgments merely to increase size.
5. **Operational guidance:** official forms, complaint portals, limitation
   tables, authority directories, and state-specific escalation paths. These
   make answers actionable, but each entry needs a review date because URLs and
   procedures change.

Every bundle should ship with golden questions, expected governing provisions,
negative/out-of-scope questions, retrieval metrics, citation checks, and a
currency review. More documents alone are not an acceptance criterion.

## What the corpus actually is

419 manifest documents. **63% are criminal law or criminal procedure.** By
category:

| documents | area |
|---:|---|
| 99 | Supreme Court judgments |
| 58 | MHA official guidance |
| 51 | rules, amendments, notifications |
| 51 | prisons and bail guidance |
| 46 | Law Commission reports |
| 26 | other relevant laws (primary) |
| 26 | special criminal laws (primary) |
| 16 | Andhra Pradesh High Court judgments |
| 12 | the three Sanhitas (BNSS, BNS, BSA) |
| 5 | legacy IPC / CrPC / Evidence Act |
| 1 | the Constitution |

Civil law is not thin — it is **absent**. Searching the manifest for the
five gap areas returns zero Acts for four of them:

| area | Acts in corpus | anything at all |
|---|---:|---|
| contract / civil obligations | 0 | 0 |
| tenancy / rent / landlord | 0 | 0 |
| consumer protection | 0 | 0 |
| noise / environmental nuisance | 0 | 0 |
| POSH / workplace harassment | 0 | 1 advisory (committee constitution only) |

Family law is the one civil area with real coverage: the Domestic Violence
Act and Rules and the Dowry Prohibition Act are all present.

## The system already handles this correctly

All five gaps are in golden set v3 with `expectation: abstain`, and the
system abstains on all five. **This is not a bug being reported — it is a
scope question.** The choice is whether to keep abstaining or to answer.

## What each gap would cost

Page counts below are **estimates from the known structure of each Act**,
not measurements — the files are not on disk to measure. Chunk estimates use
this corpus's observed ratio of roughly 3.5 chunks per page.

### 1. Contract — unblocks `contract-elements`

| document | sections | est. pages | est. chunks |
|---|---:|---:|---:|
| Indian Contract Act, 1872 | 266 | ~60 | ~210 |
| Specific Relief Act, 1963 | 44 | ~20 | ~70 |

~280 chunks. The cleanest of the five: two central Acts, both Union law,
both stable, and the question asked ("essential elements of a valid
contract") is answered almost verbatim by ss.10–30.

### 2. Consumer protection — unblocks `consumer-goods-defect`

| document | sections | est. pages | est. chunks |
|---|---:|---:|---:|
| Consumer Protection Act, 2019 | 107 | ~90 | ~315 |
| Consumer Protection (E-Commerce) Rules, 2020 | — | ~12 | ~42 |

~360 chunks. Also clean, and high value for a citizen module — defective
goods and refused refunds are among the most common citizen complaints.
The 2019 Act repealed the 1986 Act, so ingest **only** the 2019 Act or the
currency machinery will have to arbitrate a repeal you introduced yourself.

### 3. POSH / workplace harassment — unblocks `workplace-harassment`

| document | sections | est. pages | est. chunks |
|---|---:|---:|---:|
| Sexual Harassment of Women at Workplace (Prevention, Prohibition and Redressal) Act, 2013 | 30 | ~20 | ~70 |
| POSH Rules, 2013 | — | ~12 | ~42 |

~110 chunks — the **cheapest fix on this list**, and the corpus already
carries the committee-constitution advisory, so the two would join up into
a complete pathway rather than sitting alone. If only one gap is closed,
this is the one with the best ratio of value to cost.

### 4. Noise pollution — unblocks `noise-pollution`

| document | sections | est. pages | est. chunks |
|---|---:|---:|---:|
| Noise Pollution (Regulation and Control) Rules, 2000 | — | ~8 | ~28 |
| Environment (Protection) Act, 1986 | 26 | ~15 | ~53 |
| Air (Prevention and Control of Pollution) Act, 1981 | 54 | ~30 | ~105 |

~190 chunks. **Caveat:** the honest answer to "noise from a neighbouring
factory" is partly a *local* one — the Rules set day/night limits by zone,
but enforcement runs through the State Pollution Control Board and the
police under BNSS public-nuisance powers. Ingesting the Union material
answers half the question well; the other half stays state-specific.

### 5. Tenancy — unblocks `tenancy-deposit`

**This one is structurally different and I would not do it first.**

Tenancy is a **State subject**. There is no Union tenancy Act to ingest.
The Model Tenancy Act, 2021 is a template circulated to States, not law
anywhere by itself — grounding a security-deposit answer in it would be
citing something that does not bind the user's landlord.

Doing this properly means picking a State. The corpus already leans
Andhra Pradesh (16 AP High Court judgments), so:

| document | est. pages | est. chunks |
|---|---:|---:|
| AP Buildings (Lease, Rent and Eviction) Control Act, 1960 | ~35 | ~120 |
| Transfer of Property Act, 1882 (ss.105–117, leases) | ~20 | ~70 |
| Model Tenancy Act, 2021 — *reference only, label as non-binding* | ~30 | ~105 |

~190–295 chunks depending on whether the Model Act goes in. Note that
choosing a State also means the answer is only correct for that State,
which the answer would have to say. That is a product decision, not an
ingestion one.

## Recommendation

If you want the citizen module to stop abstaining on ordinary civil
questions, do them in this order — cheapest and cleanest first:

1. **POSH** (~110 chunks) — completes a pathway already half-present
2. **Contract** (~280 chunks) — two stable Union Acts, direct answer
3. **Consumer** (~360 chunks) — highest citizen value, 2019 Act only
4. **Noise** (~190 chunks) — half-answerable from Union law
5. **Tenancy** (~190–295 chunks) — needs a State decision from you first

All five is ~1,150 chunks, roughly 4% growth on the current corpus, and on
this machine an estimated 2–3 hours of ingestion.

**Doing none of them is a legitimate choice.** The system abstains correctly
today, and a criminal-law platform that says "I don't cover contract law"
is more useful than one that half-covers it. The golden set expects
abstention on all five, so **leaving them out costs zero measured score** —
closing them means rewriting those five expectations first.

## Acquisition status — 6 September 2026

You approved closing these. I went to acquire the documents from official
sources. **Three of the four hosts that carry them are unreachable from this
machine**, so the work is blocked on network access, not on a decision.

Reachable and fetched:

| document | source | state |
|---|---|---|
| Specific Relief Act, 1963 | indiacode.nic.in | 17 pages, clean English — **ready** |
| Noise Pollution (Regulation and Control) Rules, 2000 | cpcb.nic.in | 6 pages, clean English — **ready** |
| POSH Rules, 2013 | shebox.wcd.gov.in | fetched, **not fit to ingest** (see below) |

Unreachable (connection fails outright, not a 404):

| host | carries |
|---|---|
| consumeraffairs.gov.in | Consumer Protection Act, 2019 |
| wcd.nic.in | POSH Act, 2013 |
| lddashboard.legislative.gov.in | POSH Act, several others |

`indiacode.nic.in` answers, but serves only some of its own bitstreams: the
Specific Relief Act downloads, while the Contract Act, the Consumer
Protection Act, the POSH Act and the Environment (Protection) Act all return
its generic error page on every URL form and both domains.

### The POSH Rules file is a trap, and was not ingested

It is a bilingual Gazette page. Pages 1–4 are Devanagari set in a legacy 8-bit
font, which extracts as Latin gibberish — `jftLVªh laö Mhö ,yö&33004@99`.
Embedding that would put nonsense vectors in the index where they can match
nonsense queries. Only pages 5–6 are English, and they are the back half of
the rules. It is staged, with a note, and left out.

### Why the two ready files were not ingested either

Two reasons, and the second is the one that matters.

The rebuild is running. Adding to the manifest mid-run disturbs it.

More importantly, **neither file on its own closes the gap it belongs to.**
The golden set expects abstention on `contract-elements`, and the question is
"the essential elements of a valid contract" — that is Indian Contract Act
ss.10–30, which I could not get. The Specific Relief Act is about remedies for
breach. Ingesting it alone risks turning a correct abstention into a partial
answer about the wrong thing, which is worse than the abstention. Closing a
gap halfway is not closing it.

## What I need from you

**For the four unreachable documents**, either a network path to those hosts,
or the PDFs themselves dropped into
`data/legal_kb/raw/primary_law/civil_gaps/`. The list, in the order I would
ingest them:

1. Sexual Harassment of Women at Workplace (Prevention, Prohibition and Redressal) Act, 2013
2. Indian Contract Act, 1872
3. Consumer Protection Act, 2019
4. Environment (Protection) Act, 1986 and Air (Prevention and Control of Pollution) Act, 1981

**For tenancy**, still a State decision. I would take Andhra Pradesh — the
corpus already carries 16 AP High Court judgments and no other State — but
that inference is mine, not yours, and the answer is only correct for the
State chosen, which the answer would have to say.
