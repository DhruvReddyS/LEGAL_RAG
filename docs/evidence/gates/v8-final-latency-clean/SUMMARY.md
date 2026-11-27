# Latency gate, clean re-run: v8-final-latency-clean

Collection: `global_legal_corpus_v6`, commit 5d18584 (code as 7ff5e22).
Re-run of the one gate v8-final failed, on a quiet host: Low Power Mode off,
on mains, other containers at 3.5% CPU combined.

| Measure | Result | Limit | |
|---|---|---|---|
| Fast p95 | 1,576 ms | 1,758 ms | passed |
| Deep non-model overhead p95 | 2,580 ms | | passed |
| Deep first useful output p95 | 6,141 ms | | passed |
| Deep verification score | 0.788 | floor 0.717 | passed |
| Deep unsupported claims per query | 2.14 | ceiling 2.79 | passed |
| Abstention, Fast and Deep | 0.0 | | passed |
| Fast citations per query | 2.71 | floor 3.09 | **failed** |
| Deep citations per query | 3.14 | floor 3.34 | **failed** |

Context, not gated: decode 25.8 tokens/s; Deep end to end p50 38.6 s, p95 57.1 s.

## Reading the two failures

- **Fast citations** fell because commit 888f750 shows three sources instead of
  four: the fourth was relevant for 1 of 77 golden questions, and citation
  accuracy rose 0.288 -> 0.413 with the change. The floor was set when four
  were shown. This is a design change, not speed bought with evidence.
- **Deep citations** are noise at this sample size. The same code measured
  3.43, above the floor, in the v8-final run an hour earlier (21 runs of 7
  questions each time).

The contract was not re-recorded to make this pass. Doing so from this run
would also lower the Deep floor to a noisy low reading, which is what the gate
exists to prevent. A new contract should be recorded deliberately, from
several clean runs, with the three-source design stated.
