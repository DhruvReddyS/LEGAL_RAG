# Citizen demo — verified script

Every question below was run against the live system on
`global_legal_corpus_v4` and the numbers are what it actually returned, not
what it ought to return. Nothing here is aspirational.

Sign in: `demo.citizen@example.com` / `DemoCitizen#2026`
Frontend: http://localhost:3000   API: http://localhost:8000

## Before you start

Close Chrome and anything else large. The machine has 24 GB and Ollama holds
11.7 GB for the model while Docker holds 7.7 GB, so with other apps open it
swaps and every answer slows down. Expect **40 to 90 seconds** per answer on a
quiet machine; that is two LLM calls, reasoning and verification, which are
98% of the time. Retrieval itself is 2%.

Ask the first question once before the audience arrives. It loads the model;
the ones after it are faster.

## The strong five — lead with these

| Ask | Confidence | Sources | Why it lands |
|---|---|---|---|
| How do I get a certified copy of a public record from a government office? | **1.00** | 4 | The strongest answer in the set |
| My neighbour has encroached on my land. What is my remedy? | **0.95** | 2 | Civil remedy, clean structure |
| What compensation can I claim after a road accident? | **0.73** | 6 | Most sources of any question |
| Am I eligible for free legal aid? | 0.62 | 5 | Cites the Legal Services Authorities Act |
| How do I file for divorce by mutual consent? | 0.52 | 2 | Family law, plain steps |

## Reliable, use as follow-ups

| Ask | Confidence | Sources |
|---|---|---|
| The police refused to register my FIR. What are my rights? | 0.79 | 3 |
| What is the punishment for theft? | 0.50 | 3 |
| What should I do if I am arrested by the police? | 0.47 | 3 |
| My employer has not paid my wages for three months. What can I do? | 0.40 | 2 |
| How do I register a will? | 0.28 | 3 |

## The one to show deliberately

Ask **"The police refused to register my FIR. What are my rights?"** and
scroll to the bottom of the answer.

Under **Source currency** it says the sources cite provisions that were
renumbered when the 2023 Sanhitas commenced on 1 July 2024, and maps them:
CrPC s.154 is now BNSS s.173, s.156 is now s.175, s.482 is now s.528.

That is the thing worth demonstrating. A general-purpose assistant answers
this with the repealed section number and no warning. This one tells the
reader the law moved and where it moved to.

## Do not ask these

| Ask | What happens | Why |
|---|---|---|
| My landlord is not returning my security deposit | Refuses | **Correct behaviour.** The corpus holds no rent or tenancy law - zero passages. It declines rather than inventing an answer |
| I bought a defective phone and the seller refuses a refund | Refuses | A real retrieval failure. The Consumer Protection Act is indexed at 300 passages but this phrasing does not reach it |
| Someone is harassing me online | Refuses | Same: the IT Act is indexed at 300 passages and this phrasing does not reach it |

If asked about the consumer one, the honest answer is the interesting one: the
system abstains rather than answering from the nearest passage it can find,
and the nearest passage for that question was the criminal code. Rephrased as
"what are my rights as a consumer when goods are defective", it answers from
the Consumer Protection Act. The gap is between a citizen's words and the
statute's words, it is measured, and it is the next piece of work.

## If someone asks what is behind it

- 1,036 canonical documents, 49,684 indexed passages, every one traceable to
  the government page it came from
- Retrieval is hybrid: BGE-M3 dense vectors plus sparse lexical, fused by
  Qdrant server-side
- A citizen question always takes the synthesised path; the source-inspection
  path is for advocates and investigating officers
- Every published claim must name a passage that was actually retrieved. When
  the evidence does not support an answer, it says so. That is why three
  questions above refuse
