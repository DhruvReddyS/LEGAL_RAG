# Document Analyzer and Evidence Inspector acceptance

Last verified: **2026-08-27 IST**

## Implemented contract

The professional workflow now implements the specification endpoint:

```text
POST /documents/analyze?case_id={owned-case-id}
```

It accepts an already uploaded/indexed `document_id` and optional review focus.
The response contains the exact required top-level analysis fields:

```text
summary
key_clauses[]
risks[]
applicable_sections[]
```

Each clause/risk must cite one or more supplied private document chunk IDs. An
unknown chunk ID is dropped. LLM-proposed applicable sections are separately
retrieved from the verified global corpus; a proposed section is rejected unless
its section identifier resolves to a real retrieved passage. Current-law status
is conservatively shown as `status_unverified` until amendment/consolidation
review is complete.

## Role and data boundaries

- Police and Advocate accounts can analyze only indexed documents belonging to
  their own role-matched case.
- Citizen lacks the professional document-management permission.
- Cross-owner calls are rejected by the shared ownership dependency before
  document/vector access.
- Private source inspection verifies the case ID against both PostgreSQL and
  the Qdrant payload and records an audit event.
- The analysis prompt treats document text as untrusted input and ignores any
  instructions embedded inside evidence.

## Evidence Inspector

Generated research citations and every Document Analyzer finding/authority now
open a reusable **Why did the system say this?** drawer. It displays the seven
specified provenance dimensions:

1. source title/type;
2. Act/judgment and section;
3. page/chunk;
4. retrieved passage;
5. retrieval/relevance score;
6. verification status;
7. current/superseded/status-unverified state.

Private evidence is correctly labelled `not_applicable` for current-law status.
The UI never converts the corpus's conservative `is_current=false` into a false
claim that the authority is superseded.

## UI result

Police and Advocate workspaces now include a non-chat Document Analyzer workbench:

- persistent indexed evidence library;
- document classification, SHA preview, page and passage counts;
- role-specific review focus;
- structured summary, clause/fact and risk matrices;
- corpus-verified applicable-authority cards;
- visible unsupported-section rejection count and partial-review warning;
- source drawer reachable from every result;
- sidebar/command-palette shortcut `A`.

## Live acceptance

A real Police demo ran end-to-end using the host
`qwen3-14b-16k:latest` model:

| Stage/result | Measured value |
| --- | ---: |
| Uploaded fictional TXT pages | 1 |
| Private indexed chunks | 1 |
| Ollama analysis HTTP status | 201 |
| End-to-end analysis time | 46.25 s |
| Grounded key clauses | 3 |
| Grounded risks | 3 |
| Partial review | false |

The persisted demo matter is `Demo — Document Analyzer acceptance` under the
Police demo account. The automated hallucination-control test proposes
`Section 999 Imaginary Act`; it is rejected while a retrieved Section 154
authority is admitted with `status_unverified` currency qualification.

## Automated acceptance

- Full backend regression at final v0.3.0 validation: **116 passed**, one upstream Passlib/Python
  deprecation warning.
- Focused analyzer/chat/defence regression: **8 passed**.
- Next.js 14 production static export and TypeScript validation: passed.
- Tauri release compilation, local signing, `.app` and `.dmg`: passed.

## Remaining production hardening

The local Deep analysis request is synchronous and took 46.25 seconds. Before
multi-user deployment, move OCR/indexing/analysis to durable jobs, immediately
return `202`, stream/poll progress, support cancellation and isolate inference
with queue backpressure. Direct image files remain a later extension; digital
and scanned PDFs already use direct extraction with Tesseract fallback, and
UTF-8 text is supported.
