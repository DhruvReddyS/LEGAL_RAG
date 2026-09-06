# Corpus gaps — for your decision

Phase 1.7. **Nothing here has been ingested.** This lists what is missing,
sizes it, and says what each addition would buy. The decision on scope is
yours.

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

## What I need from you

Which of the five, if any — and for tenancy, which State.
