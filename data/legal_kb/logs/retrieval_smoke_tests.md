# Gold Corpus Retrieval Smoke Tests

Pipeline: BGE-M3 dense + learned sparse → Qdrant RRF → BGE reranker.
All searches are restricted to `corpus_tier = gold`.

## mandatory FIR registration

Validation: **PASS**

| # | Retrieved title | Source type | Court / Act | Section | Page | Dense | Sparse | Fused | Reranker | Tier | Official |
|---:|---|---|---|---|---:|---:|---:|---:|---:|---|---|
| 1 | Advisory on no discrimination in compulsory registration of FIRs. | GOVERNMENT_GUIDANCE | — | — | 1–3 | 0.688161 | 0.792506 | 0.7 | 0.977926 | gold | True |
| 2 | IMRAN PRATAPGADHI vs STATE OF GUJARAT Crl.A. No. 1545/2025 | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 19 | 0.611215 | — | 0.066667 | 0.965576 | gold | True |
| 3 | Advisory on Compulsory Registration of FIR u/s 154 Cr. P.C. when the information makes out a cognizable offence. | GOVERNMENT_GUIDANCE | — | — | 1–2 | 0.686978 | 0.762409 | 0.5 | 0.960212 | gold | True |
| 4 | Advisory on no discrimination in compulsory registration of FIRs. | GOVERNMENT_GUIDANCE | — | — | 2–5 | 0.66539 | 0.727148 | 0.375 | 0.955486 | gold | True |
| 5 | IMRAN PRATAPGADHI vs STATE OF GUJARAT Crl.A. No. 1545/2025 | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 21–24 | — | 0.792672 | 0.25 | 0.950227 | gold | True |

## arrest safeguards

Validation: **PASS**

| # | Retrieved title | Source type | Court / Act | Section | Page | Dense | Sparse | Fused | Reranker | Tier | Official |
|---:|---|---|---|---|---:|---:|---:|---:|---:|---|---|
| 1 | RADHIKA AGARWAL vs UNION OF INDIA W.P.(Crl.) No. 336/2018 | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 68–69 | 0.656127 | 0.704582 | 1.0 | 0.979629 | gold | True |
| 2 | ARVIND KEJRIWAL vs DIRECTORATE OF ENFORCEMENT Crl.A. No. 2493/2024 | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 11–12 | — | 0.627363 | 0.333333 | 0.958924 | gold | True |
| 3 | PANKAJ BANSAL vs UNION OF INDIA Crl.A. No. 3051-3052/2023 | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 13–15 | — | 0.57845 | 0.1 | 0.941761 | gold | True |
| 4 | RADHIKA AGARWAL vs UNION OF INDIA W.P.(Crl.) No. 336/2018 | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 71 | 0.58977 | 0.607049 | 0.290909 | 0.938237 | gold | True |
| 5 | RADHIKA AGARWAL vs UNION OF INDIA W.P.(Crl.) No. 336/2018 | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 29–30 | — | 0.604481 | 0.166667 | 0.918334 | gold | True |

## anticipatory bail

Validation: **PASS**

| # | Retrieved title | Source type | Court / Act | Section | Page | Dense | Sparse | Fused | Reranker | Tier | Official |
|---:|---|---|---|---|---:|---:|---:|---:|---:|---|---|
| 1 | Section 438 of the Code of Criminal Procedure, 1973 as Amended by the Code of Criminal Procedure (Amendment) Act, 2005 (Anticipatory Bail) 2007 Accessible_(PDF 423KB) \| Accessible_Hindi(PDF 5.11MB) | ACT | Section 438 of the Code of Criminal Procedure, 1973 as Amended by the Code of Criminal Procedure (Amendment) Act, 2005 (Anticipatory Bail) 2007 Accessible_(PDF 423KB) \| Accessible_Hindi(PDF 5.11MB) | 438 | 11–14 | 0.65209 | 0.568219 | 0.110119 | 0.981131 | gold | True |
| 2 | Section 438 of the Code of Criminal Procedure, 1973 as Amended by the Code of Criminal Procedure (Amendment) Act, 2005 (Anticipatory Bail) 2007 Accessible_(PDF 423KB) \| Accessible_Hindi(PDF 5.11MB) | ACT | Section 438 of the Code of Criminal Procedure, 1973 as Amended by the Code of Criminal Procedure (Amendment) Act, 2005 (Anticipatory Bail) 2007 Accessible_(PDF 423KB) \| Accessible_Hindi(PDF 5.11MB) | 7 | 7–11 | 0.6619 | 0.572235 | 0.153409 | 0.980167 | gold | True |
| 3 | Criminal Appeal No. No.4004/2025 12-09-2025 Anna Waman Bhalerao Vs State Of Maharashtra Justice J.b. Pardiwala And Justice R. Mahadevan Certain directions issued for disposal of bail and anticipatory bail applications – Needs to be circulated to the stake holders. | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 19–20 | 0.694449 | 0.573566 | 0.571429 | 0.969208 | gold | True |
| 4 | SHAJAN SKARIA vs THE STATE OF KERALA Crl.A. No. 2622/2024 | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 22–24 | 0.689278 | 0.588683 | 0.392857 | 0.953535 | gold | True |
| 5 | The Code of Criminal Procedure, 1973 (Act No.2 of 1974) 1996 Accessible_Vol_01(PDF 4.15MB) \| Accessible_Vol_02(PDF 3.42MB) | ACT | The Code of Criminal Procedure, 1973 (Act No.2 of 1974) 1996 Accessible_Vol_01(PDF 4.15MB) \| Accessible_Vol_02(PDF 3.42MB) | 320 | 55–56 | — | 0.613758 | 0.2 | 0.946794 | gold | True |

## default bail

Validation: **PASS**

| # | Retrieved title | Source type | Court / Act | Section | Page | Dense | Sparse | Fused | Reranker | Tier | Official |
|---:|---|---|---|---|---:|---:|---:|---:|---:|---|---|
| 1 | 25. CRLP/788/2022 2022:APHC:7432 THE STATE THROUGH CBI Vs T.GANGI REDDY AT YERRA GANGI REDDY Hon'ble Justice CHEEKATI MANAVENDRANATH ROY 16-03-2022 PDF | HIGH_COURT_JUDGMENT | High Court of Andhra Pradesh | — | 25–26 | 0.588404 | 0.633949 | 0.833333 | 0.980129 | gold | True |
| 2 | 25. CRLP/788/2022 2022:APHC:7432 THE STATE THROUGH CBI Vs T.GANGI REDDY AT YERRA GANGI REDDY Hon'ble Justice CHEEKATI MANAVENDRANATH ROY 16-03-2022 PDF | HIGH_COURT_JUDGMENT | High Court of Andhra Pradesh | — | 13 | 0.559086 | 0.594425 | 0.416667 | 0.952662 | gold | True |
| 3 | 25. CRLP/788/2022 2022:APHC:7432 THE STATE THROUGH CBI Vs T.GANGI REDDY AT YERRA GANGI REDDY Hon'ble Justice CHEEKATI MANAVENDRANATH ROY 16-03-2022 PDF | HIGH_COURT_JUDGMENT | High Court of Andhra Pradesh | — | 23–24 | — | 0.549226 | 0.142857 | 0.937897 | gold | True |
| 4 | 25. CRLP/788/2022 2022:APHC:7432 THE STATE THROUGH CBI Vs T.GANGI REDDY AT YERRA GANGI REDDY Hon'ble Justice CHEEKATI MANAVENDRANATH ROY 16-03-2022 PDF | HIGH_COURT_JUDGMENT | High Court of Andhra Pradesh | — | 1–4 | — | 0.510972 | 0.090909 | 0.933915 | gold | True |
| 5 | 25. CRLP/788/2022 2022:APHC:7432 THE STATE THROUGH CBI Vs T.GANGI REDDY AT YERRA GANGI REDDY Hon'ble Justice CHEEKATI MANAVENDRANATH ROY 16-03-2022 PDF | HIGH_COURT_JUDGMENT | High Court of Andhra Pradesh | — | 24–25 | 0.530815 | 0.562523 | 0.222222 | 0.926703 | gold | True |

## quashing FIR

Validation: **PASS**

| # | Retrieved title | Source type | Court / Act | Section | Page | Dense | Sparse | Fused | Reranker | Tier | Official |
|---:|---|---|---|---|---:|---:|---:|---:|---:|---|---|
| 1 | JAVED AHMAD HAJAM vs THE STATE OF MAHARASHTRA Crl.A. No. 886/2024 | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 1 | 0.627926 | 0.649514 | 0.666667 | 0.945601 | gold | True |
| 2 | JAVED AHMAD HAJAM vs THE STATE OF MAHARASHTRA Crl.A. No. 886/2024 | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 13–14 | 0.597031 | 0.449147 | 0.211111 | 0.936749 | gold | True |
| 3 | IMRAN PRATAPGADHI vs STATE OF GUJARAT Crl.A. No. 1545/2025 | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 54 | 0.613773 | 0.378818 | 0.180556 | 0.929951 | gold | True |
| 4 | JUST RIGHTS FOR CHILDREN ALLIANCE vs S. HARISH Crl.A. No. 2161-2162/2024 | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 146–147 | 0.61971 | 0.613228 | 0.5 | 0.929055 | gold | True |
| 5 | JUST RIGHTS FOR CHILDREN ALLIANCE vs S. HARISH Crl.A. No. 2161-2162/2024 | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 144–145 | 0.637357 | 0.675535 | 1.0 | 0.906983 | gold | True |

## electronic evidence

Validation: **PASS**

| # | Retrieved title | Source type | Court / Act | Section | Page | Dense | Sparse | Fused | Reranker | Tier | Official |
|---:|---|---|---|---|---:|---:|---:|---:|---:|---|---|
| 1 | SUNDAR @ SUNDARRAJAN vs STATE BY INSPECTOR OF POLICE R.P.(Crl.) No. 159-160/2013 In Crl.A. No. 300-301/2011 | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 20 | — | 0.413696 | 0.125 | 0.964722 | gold | True |
| 2 | SOP for Audio-Video Recording of Scene of Crime | POLICE_MANUAL | — | — | 16–18 | 0.65037 | 0.39129 | 0.119048 | 0.957517 | gold | True |
| 3 | Civil Appeal No. No.20825/2017 14-07-2020 Arjun Panditrao Khotkar Vs Kailash Kushanrao Gorantyal And Ors. R.f. Nariman, S. Ravindra Bhat And V. Ramasubramanian, Jj. We may reiterate, therefore, that the certificate required under Section 65B(4) is a condition precedent to the admissibility of evidence by way of electronic record, as correctly held in Anvar P.V. (supra), and incorrectly “clarified” in Shafhi Mohammed (supra). Oral evidence in the place of such certificate cannot possibly suffice as Section 65B(4) is a mandatory requirement of the law. Indeed, the hallowed principle in Taylor v. Taylor (1876) 1 Ch.D 426, which has been followed in a number of the judgments of this Court, can also be applied. Section 65B(4) of the Evidence Act clearly states that secondary evidence is admissible only if lead in the manner stated and not otherwise. To hold otherwise would render Section 65B(4) otiose. | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 33 | 0.650421 | 0.399285 | 0.15 | 0.930458 | gold | True |
| 4 | SOP for Audio-Video Recording of Scene of Crime | POLICE_MANUAL | — | — | 51–55 | 0.677494 | 0.45253 | 0.75 | 0.926037 | gold | True |
| 5 | Civil Appeal No. No.20825/2017 14-07-2020 Arjun Panditrao Khotkar Vs Kailash Kushanrao Gorantyal And Ors. R.f. Nariman, S. Ravindra Bhat And V. Ramasubramanian, Jj. We may reiterate, therefore, that the certificate required under Section 65B(4) is a condition precedent to the admissibility of evidence by way of electronic record, as correctly held in Anvar P.V. (supra), and incorrectly “clarified” in Shafhi Mohammed (supra). Oral evidence in the place of such certificate cannot possibly suffice as Section 65B(4) is a mandatory requirement of the law. Indeed, the hallowed principle in Taylor v. Taylor (1876) 1 Ch.D 426, which has been followed in a number of the judgments of this Court, can also be applied. Section 65B(4) of the Evidence Act clearly states that secondary evidence is admissible only if lead in the manner stated and not otherwise. To hold otherwise would render Section 65B(4) otiose. | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 44–45 | 0.6382 | 0.422124 | 0.247619 | 0.901921 | gold | True |

## POCSO

Validation: **PASS**

| # | Retrieved title | Source type | Court / Act | Section | Page | Dense | Sparse | Fused | Reranker | Tier | Official |
|---:|---|---|---|---|---:|---:|---:|---:|---:|---|---|
| 1 | JUST RIGHTS FOR CHILDREN ALLIANCE vs S. HARISH Crl.A. No. 2161-2162/2024 | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 109 | 0.541216 | 0.741108 | 0.833333 | 0.993562 | gold | True |
| 2 | JUST RIGHTS FOR CHILDREN ALLIANCE vs S. HARISH Crl.A. No. 2161-2162/2024 | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 26 | — | 0.707193 | 0.25 | 0.985828 | gold | True |
| 3 | JUST RIGHTS FOR CHILDREN ALLIANCE vs S. HARISH Crl.A. No. 2161-2162/2024 | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 29 | 0.51475 | 0.654703 | 0.267857 | 0.980986 | gold | True |
| 4 | JUST RIGHTS FOR CHILDREN ALLIANCE vs S. HARISH Crl.A. No. 2161-2162/2024 | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 29–31 | 0.53295 | 0.74146 | 0.833333 | 0.975623 | gold | True |
| 5 | Age of Consent Under The Protection of children From Sexual Offences Act,2012 17 th September 2023 Click Here | ACT | Age of Consent Under The Protection of children From Sexual Offences Act,2012 17 th September 2023 Click Here | 5 | 27–29 | 0.51282 | 0.631377 | 0.18254 | 0.959383 | gold | True |

## NDPS

Validation: **PASS**

| # | Retrieved title | Source type | Court / Act | Section | Page | Dense | Sparse | Fused | Reranker | Tier | Official |
|---:|---|---|---|---|---:|---:|---:|---:|---:|---|---|
| 1 | Criminal Appeal No.1319/2013 17-04-2025 Directorate Of Revenue Intelligence Vs Raj Kumar Arora & Ors. Justice J.b. Pardiwala Narcotic Drugs and Psychotropic Substances Act, 1985 (NDPS Act) – Scope, Interpretation, and Retrospective Application of Judicial Decisions - The interpretation of Section 8 of the NDPS Act, as clarified in Sanjeev V. Deshpande v. State, is to be applied retrospectively. The Court reaffirmed the general rule that judicial decisions operate retrospectively unless expressly limited. The absence of any invocation of the doctrine of prospective overruling in Sanjeev V. Deshpande indicates legislative intent to apply the interpretation to both past and pending cases. Consequently, all pending cases, including those instituted prior to the said decision, shall be governed by this interpretation. Retrospective application of the ruling does not violate Article 20(1) of the Constitution, as it does not create a new offence but merely clarifies the existing legal position. Overruling a prior judgment does not amount to enacting an ex post facto law, particularly where the interpretation is reasonable and foreseeable particularly where the interpretation is reasonable and foreseeable. | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 31–32 | 0.528723 | 0.61763 | 0.833333 | 0.972675 | gold | True |
| 2 | Criminal Appeal No.1319/2013 17-04-2025 Directorate Of Revenue Intelligence Vs Raj Kumar Arora & Ors. Justice J.b. Pardiwala Narcotic Drugs and Psychotropic Substances Act, 1985 (NDPS Act) – Scope, Interpretation, and Retrospective Application of Judicial Decisions - The interpretation of Section 8 of the NDPS Act, as clarified in Sanjeev V. Deshpande v. State, is to be applied retrospectively. The Court reaffirmed the general rule that judicial decisions operate retrospectively unless expressly limited. The absence of any invocation of the doctrine of prospective overruling in Sanjeev V. Deshpande indicates legislative intent to apply the interpretation to both past and pending cases. Consequently, all pending cases, including those instituted prior to the said decision, shall be governed by this interpretation. Retrospective application of the ruling does not violate Article 20(1) of the Constitution, as it does not create a new offence but merely clarifies the existing legal position. Overruling a prior judgment does not amount to enacting an ex post facto law, particularly where the interpretation is reasonable and foreseeable particularly where the interpretation is reasonable and foreseeable. | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 90–92 | — | 0.57564 | 0.142857 | 0.923592 | gold | True |
| 3 | Criminal Appeal No.1319/2013 17-04-2025 Directorate Of Revenue Intelligence Vs Raj Kumar Arora & Ors. Justice J.b. Pardiwala Narcotic Drugs and Psychotropic Substances Act, 1985 (NDPS Act) – Scope, Interpretation, and Retrospective Application of Judicial Decisions - The interpretation of Section 8 of the NDPS Act, as clarified in Sanjeev V. Deshpande v. State, is to be applied retrospectively. The Court reaffirmed the general rule that judicial decisions operate retrospectively unless expressly limited. The absence of any invocation of the doctrine of prospective overruling in Sanjeev V. Deshpande indicates legislative intent to apply the interpretation to both past and pending cases. Consequently, all pending cases, including those instituted prior to the said decision, shall be governed by this interpretation. Retrospective application of the ruling does not violate Article 20(1) of the Constitution, as it does not create a new offence but merely clarifies the existing legal position. Overruling a prior judgment does not amount to enacting an ex post facto law, particularly where the interpretation is reasonable and foreseeable particularly where the interpretation is reasonable and foreseeable. | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 93–96 | — | 0.5548 | 0.1 | 0.908618 | gold | True |
| 4 | Criminal Appeal No.1319/2013 17-04-2025 Directorate Of Revenue Intelligence Vs Raj Kumar Arora & Ors. Justice J.b. Pardiwala Narcotic Drugs and Psychotropic Substances Act, 1985 (NDPS Act) – Scope, Interpretation, and Retrospective Application of Judicial Decisions - The interpretation of Section 8 of the NDPS Act, as clarified in Sanjeev V. Deshpande v. State, is to be applied retrospectively. The Court reaffirmed the general rule that judicial decisions operate retrospectively unless expressly limited. The absence of any invocation of the doctrine of prospective overruling in Sanjeev V. Deshpande indicates legislative intent to apply the interpretation to both past and pending cases. Consequently, all pending cases, including those instituted prior to the said decision, shall be governed by this interpretation. Retrospective application of the ruling does not violate Article 20(1) of the Constitution, as it does not create a new offence but merely clarifies the existing legal position. Overruling a prior judgment does not amount to enacting an ex post facto law, particularly where the interpretation is reasonable and foreseeable particularly where the interpretation is reasonable and foreseeable. | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 45–46 | — | 0.593987 | 0.25 | 0.871912 | gold | True |
| 5 | FRANK VITUS vs NARCOTICS CONTROL BUREAU Crl.A. No. 2814-2815/2024 | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 1–2 | 0.51603 | — | 0.142857 | 0.861887 | gold | True |

## IPC to BNS mapping

Validation: **PASS**

| # | Retrieved title | Source type | Court / Act | Section | Page | Dense | Sparse | Fused | Reranker | Tier | Official |
|---:|---|---|---|---|---:|---:|---:|---:|---:|---|---|
| 1 | Handbook on Bharatiya Nyaya Sanhita, 2023 for Police Officers | GOVERNMENT_HANDBOOK | — | — | 6–9 | — | 0.539727 | 0.5 | 0.641085 | gold | True |
| 2 | Handbook on Bharatiya Nyaya Sanhita, 2023 for Police Officers | GOVERNMENT_HANDBOOK | — | — | 8–10 | 0.471904 | 0.505367 | 0.333333 | 0.497812 | gold | True |
| 3 | Handbook on Bharatiya Nyaya Sanhita, 2023 for Police Officers | GOVERNMENT_HANDBOOK | — | — | 10–13 | 0.495045 | 0.510898 | 0.833333 | 0.393385 | gold | True |
| 4 | Handbook on Bharatiya Nyaya Sanhita, 2023 for Police Officers | GOVERNMENT_HANDBOOK | — | — | 5 | — | 0.38826 | 0.090909 | 0.263979 | gold | True |
| 5 | Handbook on Bharatiya Nyaya Sanhita, 2023 for Police Officers | GOVERNMENT_HANDBOOK | — | — | 42–44 | — | 0.399256 | 0.125 | 0.191328 | gold | True |

## CrPC to BNSS mapping

Validation: **PASS**

| # | Retrieved title | Source type | Court / Act | Section | Page | Dense | Sparse | Fused | Reranker | Tier | Official |
|---:|---|---|---|---|---:|---:|---:|---:|---:|---|---|
| 1 | BNSS Handbook for Police Officers | GOVERNMENT_HANDBOOK | — | — | 12–15 | 0.5415 | 0.454095 | 0.321429 | 0.654122 | gold | True |
| 2 | VIHAAN KUMAR vs THE STATE OF HARYANA Crl.A. No. 621/2025 | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 6–9 | 0.467008 | 0.538375 | 0.191667 | 0.617916 | gold | True |
| 3 | BNSS Handbook for Police Officers | GOVERNMENT_HANDBOOK | — | — | 5–7 | 0.496324 | 0.441316 | 0.201681 | 0.563318 | gold | True |
| 4 | BNSS Handbook for Police Officers | GOVERNMENT_HANDBOOK | — | — | 3–5 | 0.564979 | 0.755816 | 0.833333 | 0.506851 | gold | True |
| 5 | MIHIR RAJESH SHAH vs THE STATE OF MAHARASHTRA Crl.A. No. 2195/2025 | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 33 | 0.582349 | 0.441915 | 0.5625 | 0.480144 | gold | True |

## Evidence Act to BSA mapping

Validation: **PASS**

| # | Retrieved title | Source type | Court / Act | Section | Page | Dense | Sparse | Fused | Reranker | Tier | Official |
|---:|---|---|---|---|---:|---:|---:|---:|---:|---|---|
| 1 | SOP for Audio-Video Recording of Scene of Crime | POLICE_MANUAL | — | — | 16–18 | 0.622337 | 0.416819 | 0.583333 | 0.523892 | gold | True |
| 2 | SOP for Audio-Video Recording of Scene of Crime | POLICE_MANUAL | — | — | 48–50 | 0.585457 | 0.417114 | 0.533333 | 0.410756 | gold | True |
| 3 | SOP for Audio-Video Recording of Scene of Crime | POLICE_MANUAL | — | — | 9 | 0.575994 | 0.384297 | 0.25 | 0.283682 | gold | True |
| 4 | IN RE : SUMMONING ADVOCATES WHO GIVE LEGAL OPINION OR REPRESENT PARTIES DURING INVESTIGATION OF CASES AND RELATED ISSUES vs SMW(Crl) No. 2/2025 | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 32 | 0.634358 | 0.48525 | 1.0 | 0.277277 | gold | True |
| 5 | SOP for Audio-Video Recording of Scene of Crime | POLICE_MANUAL | — | — | 18–20 | 0.560948 | — | 0.090909 | 0.265499 | gold | True |

## privacy constitutional criminal rights

Validation: **PASS**

| # | Retrieved title | Source type | Court / Act | Section | Page | Dense | Sparse | Fused | Reranker | Tier | Official |
|---:|---|---|---|---|---:|---:|---:|---:|---:|---|---|
| 1 | JUSTICE K.S.PUTTASWAMY(RETD) vs UNION OF INDIA W.P.(C) No. 494/2012 | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 121–123 | — | 0.570263 | 0.333333 | 0.858837 | gold | True |
| 2 | JUSTICE K.S.PUTTASWAMY(RETD) vs UNION OF INDIA W.P.(C) No. 494/2012 | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 349–353 | 0.639517 | — | 0.1 | 0.811974 | gold | True |
| 3 | JUSTICE K.S.PUTTASWAMY(RETD) vs UNION OF INDIA W.P.(C) No. 494/2012 | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 342–343 | 0.655097 | 0.510136 | 0.340909 | 0.789071 | gold | True |
| 4 | JUSTICE K.S.PUTTASWAMY(RETD) vs UNION OF INDIA W.P.(C) No. 494/2012 | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 147–149 | — | 0.510698 | 0.111111 | 0.786295 | gold | True |
| 5 | JUSTICE K.S.PUTTASWAMY(RETD) vs UNION OF INDIA W.P.(C) No. 494/2012 | SUPREME_COURT_JUDGMENT | Supreme Court of India | — | 1–5 | 0.640141 | — | 0.111111 | 0.712632 | gold | True |

## Overall validation

**PASS** — all queries returned valid, concept-matching Gold evidence.
