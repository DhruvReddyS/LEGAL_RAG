# Staged, not ingested

Fetched 6 September 2026 for the Phase 1.7 corpus gaps. **None of these is in
`canonical_documents.jsonl` and none has been ingested.** They are staged here
so the acquisition does not have to be repeated.

| file | source | pages | text | fit to ingest |
|---|---|---:|---|---|
| specific_relief_act_1963.pdf | indiacode.nic.in/bitstream/123456789/1583/7/A1963-47.pdf | 17 | clean English | yes |
| noise_pollution_rules_2000.pdf | cpcb.nic.in (Noise-Standards/noise_rules_2000.pdf) | 6 | clean English | yes |
| posh_rules_2013_shebox.pdf | shebox.wcd.gov.in/assets/uploaded_content/SH_Rules,_20132.pdf | 6 | **4 of 6 pages Hindi in a legacy font** | **no** |

The POSH Rules file is a bilingual Gazette page. Pages 1-4 are Devanagari set
in a legacy 8-bit font, which extracts as Latin gibberish
(`jftLVªh laö Mhö ,yö&33004@99`). Embedding that would put nonsense vectors in
the index and let them match nonsense queries. Only pages 5-6 are English, and
they are the back half of the rules. Ingest this only after the Hindi pages
are excluded, or replace it with an English-only text.
