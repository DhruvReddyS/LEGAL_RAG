# Civil-gap source provenance

Fetched for the Phase 1.7 corpus gaps. The five clean sources marked `yes` were
published to the `extended` tier of `global_legal_corpus_v3` on 10 September
2026. They remain outside the immutable curated `canonical_documents.jsonl`;
their intake, checksum, validation, and publication audit records are stored in
PostgreSQL. The legacy-font POSH Rules file remains excluded.

| file | source | pages | text | fit to ingest |
|---|---|---:|---|---|
| indian_contract_act_1872.pdf | indiacode.nic.in/bitstream/123456789/2187/2/A187209.pdf | 53 | clean English; sections 10, 11 and 14 detected | yes |
| specific_relief_act_1963.pdf | indiacode.nic.in/bitstream/123456789/1583/7/A1963-47.pdf | 17 | clean English | yes |
| noise_pollution_rules_2000.pdf | cpcb.nic.in (Noise-Standards/noise_rules_2000.pdf) | 6 | clean English | yes |
| posh_act_2013.pdf | spniwcd.wcd.gov.in/uploads/pdf/1710219823.pdf | 13 | clean English; complaint provision and deadline detected | yes |
| posh_rules_2013_clean.pdf | spniwcd.wcd.gov.in/uploads/pdf/1719914401_2NUqe91gql.pdf | 3 | clean English | yes |
| posh_rules_2013_shebox.pdf | shebox.wcd.gov.in/assets/uploaded_content/SH_Rules,_20132.pdf | 6 | **4 of 6 pages Hindi in a legacy font** | **no** |

Verified SHA-256 checksums for the newly staged files:

- `indian_contract_act_1872.pdf`: `d756d45a58c4cd8440e70a0189ea1fda9d7c5dfcdd6ef31a5f2ecd9cb209c59d`
- `posh_act_2013.pdf`: `abe091d5a22cf2a41659f224d45b3eb75ee37a7ac61fb4b1d094cada6a48bf24`
- `posh_rules_2013_clean.pdf`: `48469a08e87fcf94cef57d86351ae07e231699a782150396616a9fc25e9f2621`

The POSH Rules file is a bilingual Gazette page. Pages 1-4 are Devanagari set
in a legacy 8-bit font, which extracts as Latin gibberish
(`jftLVªh laö Mhö ,yö&33004@99`). Embedding that would put nonsense vectors in
the index and let them match nonsense queries. Only pages 5-6 are English, and
they are the back half of the rules. Ingest this only after the Hindi pages
are excluded, or replace it with an English-only text.
