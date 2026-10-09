# Source remediation — 2026-10-09

## Result

The canonical manifest now has a source URL for all 1,563 unique documents and marks all 1,563 as verified official. Ten local PDFs were byte-for-byte matched to the file served by the named government authority. The remaining Noise Pollution Rules extract was verified against CPCB's official current-text page without claiming byte identity.

This closes the manifest-level source gap only. Because the v5 ingestion worker loaded the manifest before these corrections, the payload gate must still prove that the corrected `source_url`, `currency_note`, `verified_official`, and `source_type` values reached every indexed point before cutover.

## Byte-identical official files

| Document | Official source | SHA-256 result |
|---|---|---|
| Indian Contract Act, 1872 | https://www.indiacode.nic.in/bitstream/123456789/2187/2/A187209.pdf | exact |
| Specific Relief Act, 1963 | https://www.indiacode.nic.in/bitstream/123456789/1583/7/A1963-47.pdf | exact |
| POSH Act, 2013 | https://www.wcd.gov.in/documents/uploaded/1710219823.pdf | exact |
| POSH Rules, 2013 | https://www.wcd.gov.in/documents/uploaded/1719914401_2NUqe91gql.pdf | exact |
| BNS to IPC comparison | https://bprd.nic.in/uploads/pdf/COMPARISON%20SUMMARY%20BNS%20to%20IPC%20.pdf | exact |
| BNSS to CrPC comparison | https://bprd.nic.in/uploads/pdf/Comparison%20summary%20BNSS%20to%20CrPC.pdf | exact |
| BSA to IEA comparison | https://bprd.nic.in/uploads/pdf/Comparison%20Summary%20BSA%20to%20IEA.pdf | exact |
| SHO booklet on the new criminal laws | https://bprd.nic.in/uploads/pdf/SHO%20Booklet%20English-Hindi-1-1.pdf | exact |
| SOP for audio-video recording under BNSS | https://bprd.nic.in/uploads/pdf/1723616060_2a3a0a30527ffcffc634.pdf | exact |
| DICGC Act and General Regulations | https://www.dicgc.org.in/sites/default/files/2025-04/dicgc-act-1961-february-2025.pdf | exact |

## Official content source

The local six-page Noise Pollution Rules file is a browser-produced extract, so byte identity is neither expected nor asserted. Its authority and current text were verified against CPCB's official implementation page:

- https://cpcb.nic.in/noise-pollution-rules/

The manifest retains `current/verify` and records a currency warning to check later Gazette amendments.

## Safety decisions

- Official guidance remains subordinate to enacted and amended legislation.
- Every remediated document retains or receives a `currency_note`; verification of provenance is not treated as proof of current law.
- The BNSS audio-video SOP is classified as `official_guidance`, not as an Act.
- No collection was switched and no baseline was re-recorded.
