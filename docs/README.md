# Corpusil documentation

Six documents. Each has one job, and together they are the whole picture.
**These are the documents we follow.** If something is not in here, it is not
agreed; if a document and the code disagree, one of the two is a bug.

| | Document | Answers |
|---|---|---|
| 01 | [PRODUCT](01-PRODUCT.md) | What Corpusil is, where it stands, every feature and its state |
| 02 | [ARCHITECTURE](02-ARCHITECTURE.md) | How it works, component by component |
| 03 | [EVIDENCE](03-EVIDENCE.md) | How it is measured, the release gates, what is still wrong |
| 04 | [OPERATIONS](04-OPERATIONS.md) | How to run it, build the corpus, cut a release |
| 05 | [RELEASE](05-RELEASE.md) | Where data lives, how it ships, the deployment stages |
| 06 | [PLAN](06-PLAN.md) | What we build next, in what order, and who owns it |

### Read in this order

New to the project: **01** then **02**.
Picking up work: **06**, then **01** §3 for the feature you are taking.
Releasing: **03** for the gates, then **04** and **05**.

### What is not here

- `evidence/` — the measured evidence trail. The gate runner writes into it and
  it is the record a release is justified by. Machine-written; do not hand-edit.
- `paper/`, `presentations/`, `INTERVIEW_PREP.md`,
  `RND_PRESENTATION_RAG_FROM_ZERO_TO_ADVANCED.md` — academic deliverables, a
  different audience and a different purpose.
- `architecture/`, `demo/` — diagrams and the demo script.

### Rules for these documents

1. **Measured, not remembered.** Every number states what it was measured
   against and when. A number without that is a guess wearing a suit.
2. **One place per fact.** A fact lives in exactly one document; the others
   link to it. This is why the previous fourteen documents became six.
3. **Features have identifiers.** `01-PRODUCT` §3 is the catalogue. Work refers
   to `P-05` or `WEB-02`, not to a paraphrase.
4. **A gap is written down as a gap**, with what it would cost to close. A
   document that only lists what works is marketing.
