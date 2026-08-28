# Source materials

This directory contains source files that are **not part of the active Gold
corpus**. It keeps archival downloads out of the repository root and prevents
unreviewed PDFs from being indexed accidentally.

## Layout

```text
candidate_imports/
  primary_law/          Acts, codes, Constitution, and criminal-law books
  comparison_guides/    Legacy-to-new-law comparison documents
  training_guidance/    Police/training reference material
  unclassified_scans/   Scanned downloads requiring manual identification
legacy_collections/
  global_legal_knowledge_base/  Earlier curated folder tree and its metadata
```

Organization snapshot (2026-08-21): 151 PDFs total—134 in the legacy
collection and 17 candidate imports. SHA-256 comparison found 7 candidate
imports already present byte-for-byte in Gold and 10 candidates not present in
the frozen Gold manifest. No PDF from the active Gold tree was moved.

The legacy collection's CSV and download reports intentionally retain the
absolute paths recorded when that collection was created. Those paths are
historical provenance, not current operational destinations; use this
directory tree when browsing the archived files.

The active, immutable corpus is [`../legal_kb`](../legal_kb/README.md). Its 419
physical PDFs are checksum-tracked under `legal_kb/raw`, and its ingestion
manifests refer only to paths inside `legal_kb`.

## Promotion rule

Never copy a candidate directly into `legal_kb/raw`. A future corpus version
must first establish an official source URL, SHA-256 checksum, title, authority,
document type, jurisdiction, legal/effective status, language, page count, and
duplicate relationship. Then regenerate a versioned manifest and preserve the
old Gold corpus for reproducibility.

Some candidate files are byte-identical to documents already in Gold; they are
retained here only as source-history copies. Others are not in Gold and remain a
backlog until provenance and quality review are complete.

Do not infer identity from filenames. In particular, the candidate named
`Code of Criminal Procedure, 1973.pdf` is byte-identical to Gold's two-page 2010
CrPC amendment PDF, not a complete CrPC bare Act. It must be renamed only after
metadata review and must not be promoted as the full Code.
