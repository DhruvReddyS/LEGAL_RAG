# Corpus Diversity and Expansion Report

Date: 10 September 2026  
Live collection: `global_legal_corpus_v3`  
Live points: 25,323 (24,810 curated Gold + 513 extended)

## 1. Executive verdict

The concern is correct: the corpus is large enough to look substantial but is
not diverse enough for a general citizen legal-assistance product.

The curated manifest contains 419 physical documents representing 381 unique
documents. About 63% concerns criminal law or criminal procedure. Of the 419
manifest rows, 403 (96.2%) are central-jurisdiction material and only 16 (3.8%)
are Andhra Pradesh High Court judgments. All 419 are English. There are no
curated consumer, mainstream tenancy, motor-vehicle, environment, health,
disability, or ordinary employment-law bundles.

Five official sources have now closed part of the contract, noise, and POSH
gaps, but that adds only 513 points. It does not turn the corpus into broad
citizen-law coverage.

The right next step is not “download as many legal PDFs as possible.” It is to
build complete, versioned **answer bundles**. Each bundle should include:

1. The governing Act.
2. Current rules, amendments, and commencement notifications.
3. State-specific law where jurisdiction changes the answer.
4. Official complaint forms, portals, authority information, and procedure.
5. A small set of decisions that resolve recurring interpretation questions.
6. Golden questions, governing-provision expectations, and negative tests.

## 2. Measured baseline

### Corpus composition

| Measure | Current value | Consequence |
|---|---:|---|
| Physical manifest documents | 419 | Size alone overstates breadth |
| Unique canonical documents | 381 | 38 physical rows are duplicates/alternates |
| Live extended documents | 5 | Contract, Specific Relief, Noise Rules, POSH Act and Rules |
| Curated central jurisdiction | 403 (96.2%) | State-law questions are usually unanswerable |
| Curated Andhra Pradesh | 16 (3.8%) | Only AP judgments; almost no AP statutes/rules/processes |
| Curated judgments | 115 (27.4%) | 99 Supreme Court and 16 AP High Court |
| Curated Acts | 90 | Concentrated in criminal/special-criminal law |
| Advisories/guidance/SOPs | 123+ | Strong operational criminal-law bias |
| Languages | 419 English, 0 others | Telugu/Hindi citizen phrasing is not represented |
| Currency labels | all require some form of verification | Current-law confidence remains a major risk |

### Evaluation composition

Golden set v3 has 61 questions:

| Slice | Questions | Share |
|---|---:|---:|
| Citizen | 29 | 47.5% |
| Police | 25 | 41.0% |
| Advocate | 7 | 11.5% |

Contract, tenancy, environment, consumer, and workplace law have only one
question each. Health, disability, banking, motor accidents, inheritance,
employment, RTI, RERA, civil filing, and senior-citizen rights have no useful
evaluation slice. This means the current score cannot represent general
citizen usefulness.

## 3. Domain coverage scorecard

Grades describe usable question coverage, not whether a title containing a
keyword exists.

| Domain | Grade | What exists | Main missing material |
|---|---:|---|---|
| Criminal procedure, arrest, FIR, bail | A- | BNSS, BNS, BSA, legacy mappings, guidance, judgments | Three governing-provision reach gaps and state police procedure |
| Constitutional rights | C+ | Constitution and selected Supreme Court judgments | Topic-balanced rights cases and practical remedy/filing pathways |
| Child protection | B | POCSO/JJ-related law and substantial guidance | State authorities, forms, compensation, and current operational routes |
| Domestic violence/dowry | B- | DV Act/Rules and Dowry Act | Maintenance, family court, protection officer, shelter, and AP process bundle |
| Contract/remedies | C | Contract Act and Specific Relief Act now live | Sale of Goods, Partnership, Arbitration, Limitation, CPC remedies |
| POSH/workplace harassment | B- | POSH Act, Rules, committee advisory | Current forms, local committee directories, selected interpretation cases |
| Noise/environment | D+ | Noise Rules only | Environment Act, amendments, CPCB/APPCB process and local enforcement |
| Consumer/e-commerce | F | No usable curated bundle | 2019 Act, rules, CCPA guidance, complaint process, e-Daakhil |
| Tenancy/housing/property | F | No usable binding bundle | AP Tenancy Act/Rules, TPA leases, RERA/APRERA, registration/stamp guidance |
| Civil procedure/remedies | F | Legal Services Authorities Act only | CPC, Limitation, Evidence/application rules, mediation, court filing |
| Family/inheritance | D | DV/Dowry and Child Marriage only | Marriage, succession, adoption, guardianship, maintenance, Family Courts |
| Employment/labour | F | One child-labour advisory | Four current labour codes, current rules/notifications, AP rules, portals |
| Banking/payments/cheque disputes | F | Isolated judgment references | NI Act, payment systems, RBI Ombudsman, failed-transaction and fraud guidance |
| Cyber/data/platform rights | D+ | IT Act and a few legacy cyber notifications | IT Rules 2021 updates, DPDP Act/Rules/timeline, cybercrime reporting process |
| Motor vehicles/accident claims | F | Nothing usable | MV Act/Rules, compensation procedure, insurer duties, MACT forms/cases |
| Health/mental health/disability | F | Nothing usable | Mental Healthcare Act/Rules, RPwD Act/Rules, patient complaint pathways |
| Senior citizens | F | Nothing usable | Senior Citizens Act, AP Rules/tribunals, property and maintenance process |
| RTI/public services | F | Constitution only | RTI Act/Rules, CIC guidance, AP information commission process |
| Legal aid/court access | D+ | Legal Services Authorities Act and one NALSA source | Eligibility, applications, Lok Adalat, victim compensation, e-filing forms |

## 4. Why many answers remain unsatisfactory

### 4.1 The governing law is absent

No retrieval or model improvement can answer a tenancy, consumer, motor
accident, disability, or wage question safely when the governing bundle is not
indexed. The correct behaviour is abstention, which feels unsatisfactory but
is safer than inventing an answer.

### 4.2 Isolated Acts do not provide an actionable answer

An Act may define a right, while rules specify the form, deadline, authority,
fee, jurisdiction, and appeal. A citizen usually asks “what should I do next?”
rather than “what does section X say?” Answers need both primary law and
official operational guidance.

### 4.3 State law is almost absent

Tenancy, land, court fees, police implementation, labour rules, victim
compensation, local authorities, and filing procedure can vary by State. A
96.2% central corpus cannot safely answer these as if one national procedure
applied everywhere.

### 4.4 Currency is not fully resolved

All 419 curated rows carry a status that still includes a verification
qualification. New labour and data-protection regimes have commencement and
transition timelines. Every source needs effective dates, amendment lineage,
repeal/replacement links, and a reviewed-at date.

### 4.5 The corpus mixes authority and commentary unevenly

There are many MHA advisories and Law Commission reports but few civil
statutes, rules, forms, or state procedures. Commentary should never outrank
the governing provision merely because it uses the citizen's words more often.

### 4.6 The evaluation set hides domain failure

One question cannot validate a legal domain. Each bundle needs direct,
colloquial, procedural, scenario, deadline, jurisdiction, exception, and
out-of-scope questions.

## 5. Recommended acquisition programme

## Phase A — highest citizen value

Target: approximately 50-75 official documents and 3,000-5,000 well-formed
chunks. Expected curation and validation effort: 3-7 focused working days.
One-time CPU embedding on the current machine is likely to take roughly 1-3
hours depending on document length; this must run separately from live Deep
RAG benchmarking.

### A1. Consumer and e-commerce

Add as one bundle:

- Consumer Protection Act, 2019.
- Consumer Protection (Consumer Disputes Redressal Commissions) Rules, 2020.
- Consumer Protection (E-Commerce) Rules, 2020 and current amendments.
- Consumer Protection (Direct Selling) Rules, 2021.
- Jurisdiction and mediation rules/regulations.
- CCPA misleading-advertisement guidelines.
- CCPA dark-pattern guidelines and current amendments.
- National Consumer Helpline and e-Daakhil official procedure/help material.

Questions unlocked: defective goods, denied refunds, online marketplace
liability, misleading advertisements, dark patterns, service deficiency,
where to complain, pecuniary/territorial jurisdiction, mediation, and appeal.

Official starting point: [Department of Consumer Affairs consumer-protection
hub](https://consumeraffairs.nic.in/acts-and-rules/consumer-protection/consumer-protection).
The Department's [dark-pattern guidelines](https://consumeraffairs.nic.in/sites/default/files/The%20Guidelines%20for%20Prevention%20and%20Regulation%20of%20Dark%20Patterns%2C%202023.pdf)
are a high-value companion source.

### A2. Andhra Pradesh tenancy, leases, and housing

Add with explicit jurisdiction labels:

- Andhra Pradesh Residential and Non-Residential Premises Tenancy Act, 2017.
- Commencement notification, current AP Rules, amendments, and Rent Authority
  information. Verify these before publication because India Code currently
  marks the State content as under update.
- Transfer of Property Act, 1882, especially sections 105-117 on leases.
- Real Estate (Regulation and Development) Act, 2016.
- Andhra Pradesh RERA Rules, forms, complaint instructions, and appeal route.
- Registration and stamp-duty guidance from the AP registration department.
- A small set of current AP High Court tenancy/RERA decisions.

Do not present the Model Tenancy Act as binding law. The official [AP tenancy
Act page](https://www.indiacode.nic.in/indiacode/handle/123456789/3902?view_type=browse)
states that its content is under update, while the [AP RERA Rules](https://rera.ap.gov.in/RERA/DOCUMENTS/gos/1.MS115%20_27032017_AP%20Rules%202017.PDF)
and [APRERA citizen services](https://rera.ap.gov.in/RERA/Views/ourservices_tel.aspx)
provide usable official State material.

### A3. Civil remedies and court access

Add:

- Code of Civil Procedure, 1908, including Orders and Schedules.
- Limitation Act, 1963 and its Schedule.
- Arbitration and Conciliation Act, 1996 with current amendments.
- Mediation Act, 2023 and commencement material.
- Commercial Courts Act where relevant.
- AP civil rules of practice, court-fee law, e-filing rules, and current forms.
- NALSA legal-aid eligibility, application, Lok Adalat, mediation, and victim
  compensation material.

Official sources include the [CPC PDF](https://www.indiacode.nic.in/bitstream/123456789/2191/1/eng.pdf),
[Limitation Act](https://www.indiacode.nic.in/indiacode/handle/123456789/1565?view_type=browse),
[NALSA](https://nalsa.gov.in/), [eCourts e-filing](https://filing.ecourts.gov.in/pdedev/?p=otherPages%2FaboutUs),
and the [AP High Court Gazette/rules page](https://aphc.gov.in/Gazette_Publications.php).

### A4. Banking, digital payments, and cheque disputes

Add:

- Negotiable Instruments Act, 1881, especially sections 138-148.
- Payment and Settlement Systems Act, 2007.
- RBI Integrated Ombudsman Scheme, current amendments, FAQs, complaint form,
  covered entities, and Complaint Management System instructions.
- RBI failed-transaction reversal/compensation directions.
- Official cyber-financial-fraud reporting and immediate-response guidance.
- Selected Supreme Court decisions on cheque notice, limitation, jurisdiction,
  company liability, and compounding.

Official sources: [Negotiable Instruments Act](https://www.indiacode.nic.in/handle/123456789/13092?view_type=browse),
[Payment and Settlement Systems Act](https://www.indiacode.nic.in/indiacode/handle/123456789/2082?view_type=search),
and [RBI Integrated Ombudsman Scheme](https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=12192&Mode=0).

### A5. Motor vehicles and accident compensation

Add:

- Motor Vehicles Act, 1988 with amendments.
- Central Motor Vehicles Rules and relevant AP rules.
- MACT filing forms and eCourts material.
- IRDAI/insurer claim-process guidance from official sources.
- Selected binding decisions on multiplier, future prospects, negligence,
  insurer liability, hit-and-run compensation, and limitation.

Official starting point: [Motor Vehicles Act on India Code](https://www.indiacode.nic.in/handle/123456789/13700).

## Phase B — rights and daily-life coverage

Target: another 50-80 official documents and 3,000-6,000 chunks.

### B1. Family, inheritance, guardianship, and maintenance

- Hindu Marriage Act, 1955 and current rules.
- Hindu Succession Act, 1956.
- Hindu Adoptions and Maintenance Act, 1956.
- Hindu Minority and Guardianship Act and Guardians and Wards Act.
- Special Marriage Act, Family Courts Act, and relevant rules.
- Current maintenance provisions, including BNSS section 144.
- AP Family Court procedures and forms.

Official starting points: [Hindu Marriage Act](https://www.indiacode.nic.in/handle/123456789/17272?sam_handle=123456789%2F2517&view_type=search),
[Hindu Succession Act](https://www.indiacode.nic.in/handle/123456789/17273?sam_handle=123456789%2F2517),
and [Hindu Adoptions and Maintenance Act](https://www.indiacode.nic.in/indiacode/handle/123456789/1638?view_type=browse).

### B2. Employment and labour

- Code on Wages, 2019.
- Industrial Relations Code, 2020.
- Code on Social Security, 2020.
- Occupational Safety, Health and Working Conditions Code, 2020.
- Commencement notifications, current central rules, AP rules, and transition
  guidance for the 29 replaced laws.
- Official wage-claim, gratuity, maternity, EPFO, ESIC, and SAMADHAN procedures.

Currency review is mandatory. The Ministry announced implementation of the
four codes from 21 November 2025, so older Acts and new Codes need explicit
effective-date and replacement metadata. See the [Ministry implementation
announcement](https://labour.gov.in/sites/default/files/pib2192463.pdf) and
[Code on Wages](https://www.indiacode.nic.in/indiacode/handle/123456789/15793?view_type=browse).

### B3. Health, mental health, and disability

- Mental Healthcare Act, 2017 and all central rules.
- Rights of Persons with Disabilities Act, 2016 and Rules, 2017.
- Clinical Establishments and patient grievance material where applicable.
- AP State authorities, boards, commissioner information, forms, and appeals.
- A small rights-focused judgment set.

Official sources: [Mental Healthcare Act and Rules](https://www.indiacode.nic.in/handle/123456789/2249?view_type=browse)
and [Rights of Persons with Disabilities Act and Rules](https://www.indiacode.nic.in/handle/123456789/13684?locale=en).

### B4. Senior-citizen protection

- Maintenance and Welfare of Parents and Senior Citizens Act, 2007.
- AP Rules, Maintenance Tribunal information, applications, and appeals.
- Selected decisions on section 23 property transfers and maintenance.

Official starting point: [Senior Citizens Act](https://www.indiacode.nic.in/handle/123456789/13696?locale=en).

### B5. RTI and administrative remedies

- Right to Information Act, 2005 and Rules.
- Central Information Commission guides, forms, fees, exemptions, first appeal,
  second appeal, and complaint procedure.
- AP Information Commission rules and routes.
- Public grievance and department-specific appellate mechanisms, each labelled
  as guidance rather than primary law.

## Phase C — digital and environmental completeness

### C1. Cyber, platforms, and data protection

- Keep the existing IT Act but add current amendments and active rules.
- Information Technology (Intermediary Guidelines and Digital Media Ethics
  Code) Rules, 2021 with all current amendments.
- Digital Personal Data Protection Act, 2023.
- DPDP Rules, 2025, corrigendum, enforcement timeline, and Data Protection
  Board material.
- Official cybercrime portal process, preservation guidance, and reporting
  routes.

The DPDP rollout is phased, so one blanket `is_current=true` flag is unsafe.
Use provision-level effective dates from the [MeitY DPDP Rules and enforcement
timeline page](https://www.meity.gov.in/documents/act-and-policies/digital-personal-data-protection-rules-2025-gDOxUjMtQWa?pageTitle=Digital-Personal-Data-Protection-Rules-2025%3B)
and the [MeitY Acts and Policies hub](https://www.meity.gov.in/documents/act-and-policies).

### C2. Environment and local nuisance

- Environment (Protection) Act, 1986.
- Current Noise Rules amendments and CPCB standards/guidance.
- Air and Water Acts for pollution complaints.
- AP Pollution Control Board complaint, consent, inspection, and appeal routes.
- Municipal nuisance and police enforcement material, correctly jurisdiction
  labelled.

Official starting points: [Environment Protection Act](https://www.indiacode.nic.in/handle/123456789/13655?view_type=browse)
and [CPCB Noise Rules](https://cpcb.nic.in/noise-pollution-rules/).

### C3. Real estate and homebuyers

- RERA Act, AP Rules, forms, APRERA complaint flow, orders, and appeal process.
- Selected AP RERA/Appellate Tribunal and constitutional-court decisions.

Official sources: [RERA Act](https://www.indiacode.nic.in/indiacode/handle/123456789/2158?view_type=browse)
and [APRERA](https://rera.ap.gov.in/RERA/Views/about_tel.aspx).

## 6. Judgment acquisition strategy

Do not bulk-ingest thousands of judgments. That increases duplicate facts,
weak headnotes, retrieval competition, and currency work.

For each bundle, begin with 5-15 cases selected because they answer a recurring
interpretation question that the statute does not settle. Prefer:

1. Constitution Bench/Supreme Court binding authorities.
2. Recent Supreme Court clarifications.
3. Andhra Pradesh High Court decisions for AP procedure/state law.
4. Full official judgment text, not third-party summaries.
5. Cases with neutral citation, decision date, bench, status, and treatment
   metadata.

Add citation graph links (`follows`, `distinguishes`, `overrules`, `applies`)
before adding more cases on the same issue.

## 7. Language and accessibility expansion

The present corpus is 100% English. For a citizen module aimed at Andhra
Pradesh, the first language expansion should be Telugu, then Hindi.

Do not mix machine translations into the authoritative text field. Store:

- Official source text unchanged.
- Official Telugu/Hindi version where available.
- A separately labelled plain-language explanation.
- Translation provenance and review status.
- Cross-language aliases for legal and colloquial terms.

Start evaluation with Telugu/Hinglish/Tenglish queries retrieving English
authority. Only publish translated answers after citation alignment tests show
that translated claims still map to the same provision.

## 8. Required metadata for every new source

At minimum:

- Stable document and canonical IDs.
- Official source URL and publisher.
- SHA-256 and acquisition timestamp.
- Act/rule/guidance/judgment/form classification.
- Central/State/local jurisdiction.
- Act name, section, subsection, rule, schedule, and heading path.
- Enactment, commencement, effective-from, effective-to, and reviewed-at dates.
- Amendment, repeal, replacement, and supersession links.
- Binding authority level and court hierarchy.
- Language and translation status.
- Corpus tier, quality gate, OCR warnings, and extraction coverage.
- Operational URL review date for forms and portals.

An extended source must not automatically be considered current merely because
it came from an official HTTPS URL. Currency needs an independent gate.

## 9. Evaluation expansion

Before Phase A is accepted, expand from 61 to at least 200 questions. Target
300-500 after Phase C.

Each domain should initially have 12-20 questions covering:

- Plain definition.
- Eligibility and applicability.
- Step-by-step procedure.
- Deadline/limitation.
- Correct authority/forum.
- Documents/forms/fees.
- Exceptions and defences.
- Central versus AP jurisdiction.
- Current versus repealed law.
- Colloquial and misspelled phrasing.
- A genuinely absent or foreign-jurisdiction question.
- A question requiring abstention or clarification.

Track at least:

- Governing-provision reach at 5/20/100.
- Recall and precision by domain and role.
- Citation accuracy and authority quality.
- Currency correctness.
- Required-ground coverage.
- Abstention correctness.
- Actionability: authority, deadline, next step, and required documents.
- Reading level and answer length.
- Fast/Deep stage timing and cold/cache-warm timing.

## 10. Sources that should not be added

- Legal blogs or SEO explainers as authority.
- Random scraped headnotes without the official judgment.
- Repealed Acts without effective-date and replacement metadata.
- Draft rules mixed with final rules.
- The Model Tenancy Act labelled as binding State law.
- Entire court archives without issue selection and precedent treatment.
- PDFs with corrupt legacy-font extraction.
- Duplicate mirrors of the same Gazette document.
- Dynamic portal pages without a capture/review timestamp.
- Private citizen documents in the global corpus.

## 11. Recommended target state

A practical next release should aim for:

- 10-12 properly covered citizen domains.
- 150-250 additional primary-law/rule/guidance/form documents.
- 100-150 issue-selected judgments, not a bulk dump.
- Central plus Andhra Pradesh law for every State-sensitive bundle.
- Telugu query support and an initial Telugu official-source slice.
- 300-500 balanced golden questions.
- No publication unless governing-provision reach, citation accuracy,
  abstention, currency, and latency gates pass by domain.

The success measure is not one million vectors. It is the percentage of real
citizen question classes for which the system can retrieve the governing law,
state the correct current procedure, cite the right authority, and decline
when jurisdiction or facts are missing.

## 12. Immediate recommendation

The best next acquisition sprint is:

1. Consumer/e-commerce.
2. AP tenancy + TPA leases + AP RERA.
3. CPC + Limitation + NALSA/eCourts access.
4. Banking/payments/cheque disputes.
5. Motor vehicles/accident compensation.

These five bundles address common citizen problems, diversify the corpus away
from criminal law, and create testable end-to-end workflows. Family,
employment, health/disability, senior-citizen, RTI, DPDP, and complete
environmental coverage should follow as Phase B/C rather than being mixed into
one uncontrolled import.
