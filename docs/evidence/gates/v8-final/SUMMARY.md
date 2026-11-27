# Corpus gates: v8-final

Collection: `global_legal_corpus_v6`
Run: 2026-11-27T06:22:56Z
Commit: 7ff5e22

| Gate | Result |
|---|---|
| payload | passed |
| retrieval | passed |
| answers | passed |
| provision | passed |
| health | passed |
| provisions | passed |
| latency (exit 1) | **FAILED** |

Per-gate output is beside this file.

## Notes on this run

- The first latency attempt never measured: the benchmark registers throwaway
  accounts, and the password supplied was 11 characters against the API's
  minimum of 12, so /auth/register returned 422. It was re-run alone with a
  valid password; the other six gates were not repeated.
- The re-run failed on two counts, both with a known cause:
  - fast_citations_per_query 2.71 against a floor of 3.09. Commit 888f750
    deliberately shows three Fast sources instead of four, because the fourth
    was relevant for 1 of 77 questions. Citation accuracy rose 0.288 -> 0.413
    in the retrieval gate above. The floor was set when four were shown.
  - fast_p95_ms 2,163 against 1,758. The host was in macOS Low Power Mode and
    another project's 14 containers were running: decode fell to 13.8 tokens/s
    against 23.6 on the clean 6 Nov run, and Deep p50 rose to 76 s from 46 s.
- Deep quality improved: verification score 0.810 (floor 0.717), unsupported
  claims per query 2.0 (ceiling 2.79), no ungrounded answer published.
