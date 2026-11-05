#!/usr/bin/env python3
"""Build golden set v4, and refuse any item the corpus does not bear out.

v3 asked whether a passage mentioned a phrase, so a judgment quoting a section
satisfied the item while the section itself was absent. Here an item names the Act
and section that govern the question, and each is verified by parsing the cached
text of that Act and checking the section really says what the item assumes.

Items were written from the statutes rather than from what retrieval returns, and
must not be edited to suit a result.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.ingestion.extract import ExtractedDocument  # noqa: E402
from app.ingestion.classifier import LegalDocumentType  # noqa: E402
from app.ingestion.structure import parse_legal_structure  # noqa: E402

KB = ROOT / "data" / "legal_kb"
OUT = KB / "evaluation" / "golden_set_v4.json"

BNS, BNSS, BSA = "nyaya sanhita", "nagarik suraksha", "sakshya adhiniyam"
CON = "constitution of india"


def s(act: str, section: str, words: str) -> dict:
    return {"act": act, "section": section, "verify": words}


# id, role, topic, question, governing provisions
ITEMS: list[tuple[str, str, str, str, list[dict]]] = [
    # ---- Constitution
    ("art19-speech", "citizen", "constitutional", "What limits can the government place on freedom of speech?", [s(CON, "19", "reasonable restrictions")]),
    ("art14-equality", "citizen", "constitutional", "Does the Constitution guarantee equal treatment by the State?", [s(CON, "14", "equal")]),
    ("art21-life", "citizen", "constitutional", "Can the State take away my life or liberty without following law?", [s(CON, "21", "personal liberty")]),
    ("art22-detention", "citizen", "constitutional", "What protection does a person have if they are detained without trial?", [s(CON, "22", "detention")]),
    ("art17-untouchability", "citizen", "constitutional", "Is untouchability prohibited by law?", [s(CON, "17", "untouchability")]),
    ("art21a-education", "citizen", "constitutional", "Do children have a right to free education?", [s(CON, "21A", "education")]),
    ("art32-remedy", "advocate", "constitutional", "Which constitutional provision lets a person approach the Supreme Court to enforce a fundamental right?", [s(CON, "32", "Supreme Court")]),
    ("art226-writ", "advocate", "constitutional", "What is the power of High Courts to issue writs?", [s(CON, "226", "writs")]),
    # ---- BNS, in the words people use
    ("bns-theft", "citizen", "criminal", "Someone took my phone without asking. What offence is that?", [s(BNS, "303", "theft")]),
    ("bns-theft-current", "citizen", "currency", "Which law now governs the offence of theft?", [s(BNS, "303", "theft")]),
    ("bns-cheating", "citizen", "criminal", "A person tricked me into paying money for something false. Which offence covers that?", [s(BNS, "318", "cheat")]),
    ("bns-murder-punishment", "citizen", "criminal", "What is the punishment for murder?", [s(BNS, "103", "murder")]),
    ("bns-stalking", "citizen", "criminal", "A man keeps following a woman and contacting her against her wishes. Is that an offence?", [s(BNS, "78", "stalking")]),
    ("bns-sexual-harassment", "citizen", "criminal", "What counts as sexual harassment under the criminal law?", [s(BNS, "75", "sexual")]),
    ("bns-cruelty", "citizen", "criminal", "Is cruelty by a husband or his relatives a crime?", [s(BNS, "85", "cruelty")]),
    ("bns-dowry-death", "citizen", "criminal", "What is dowry death?", [s(BNS, "80", "dowry")]),
    ("bns-intimidation", "citizen", "criminal", "Someone threatens to harm me unless I do what they say. Which offence is that?", [s(BNS, "351", "intimidation")]),
    ("bns-defamation", "citizen", "criminal", "Is spreading false statements that damage my reputation an offence?", [s(BNS, "356", "defam")]),
    ("bns-community-service", "citizen", "criminal", "Is community service available as a punishment under the new criminal law?", [s(BNS, "4", "community service")]),
    ("bns-abetment-suicide", "advocate", "criminal", "What is the offence of abetment of suicide?", [s(BNS, "108", "suicide")]),
    ("bns-organised-crime", "advocate", "criminal", "How does the law define organised crime?", [s(BNS, "111", "organised crime")]),
    ("bns-snatching", "police", "criminal", "Which provision covers snatching?", [s(BNS, "304", "snatching")]),
    ("bns-robbery", "police", "criminal", "When does theft become robbery?", [s(BNS, "309", "robbery")]),
    ("bns-kidnapping", "police", "criminal", "How is kidnapping defined?", [s(BNS, "137", "kidnap")]),
    # ---- BNSS: arrest and detention
    ("bnss-arrest-no-warrant", "police", "procedure", "When can police arrest a person without a warrant?", [s(BNSS, "35", "without a warrant")]),
    ("bnss-arrest-current", "police", "currency", "Which law now governs arrest without a warrant?", [s(BNSS, "35", "without a warrant")]),
    ("bnss-arrest-woman", "police", "procedure", "What safeguards apply when a woman is arrested?", [s(BNSS, "43", "woman")]),
    ("bnss-handcuff", "citizen", "procedure", "Are the police allowed to handcuff a person?", [s(BNSS, "43", "handcuff")]),
    ("bnss-grounds", "police", "procedure", "Must the grounds of arrest be communicated to the arrested person?", [s(BNSS, "47", "grounds")]),
    ("bnss-inform-relative", "citizen", "procedure", "My brother was arrested. Do the police have to tell our family?", [s(BNSS, "48", "arrest")]),
    ("bnss-produce-24h", "citizen", "procedure", "How long can police hold someone before taking them to a magistrate?", [s(BNSS, "58", "twenty-four hours")]),
    ("bnss-medical-exam", "police", "procedure", "When may an accused person be medically examined?", [s(BNSS, "51", "medical")]),
    ("bnss-identification", "police", "procedure", "How should a test identification parade be conducted?", [s(BNSS, "54", "identif")]),
    ("bnss-remand", "police", "procedure", "What is the difference between police custody and judicial custody during remand?", [s(BNSS, "187", "custody")]),
    # ---- BNSS: FIR and investigation
    ("bnss-fir", "citizen", "procedure", "How do I file an FIR?", [s(BNSS, "173", "cognizable")]),
    ("bnss-fir-refused", "citizen", "procedure", "The police refuse to register my FIR. What can I do?", [s(BNSS, "173", "Superintendent")]),
    ("bnss-case-diary", "police", "procedure", "How must a case diary be maintained during an investigation?", [s(BNSS, "192", "diary")]),
    ("bnss-final-report", "police", "procedure", "What does a final report to the magistrate contain?", [s(BNSS, "193", "report")]),
    ("bnss-inquest", "police", "procedure", "What is the procedure for an inquest into an unnatural death?", [s(BNSS, "194", "suicide")]),
    ("bnss-custody-death", "police", "procedure", "What must happen after a death in police custody?", [s(BNSS, "196", "custody")]),
    ("bnss-search-record", "police", "procedure", "When must a search or seizure be videographed?", [s(BNSS, "105", "audio-video")]),
    ("bnss-search-officer", "police", "procedure", "When may a police officer search without a warrant during an investigation?", [s(BNSS, "185", "search")]),
    ("bnss-seizure", "police", "procedure", "When may police seize property?", [s(BNSS, "106", "seize")]),
    ("bnss-produce-document", "police", "procedure", "How can police require someone to produce a document or a phone?", [s(BNSS, "94", "produc")]),
    ("bnss-victim-compensation", "citizen", "procedure", "Can a victim of crime receive compensation?", [s(BNSS, "396", "compensation")]),
    # ---- BNSS: bail
    ("bnss-default-bail", "citizen", "bail", "What is default bail?", [s(BNSS, "187", "released on bail")]),
    ("bnss-anticipatory", "citizen", "bail", "On what grounds may anticipatory bail be granted?", [s(BNSS, "482", "bail")]),
    ("bnss-bail-non-bailable", "advocate", "bail", "When may a person accused of a non-bailable offence be released on bail?", [s(BNSS, "480", "non-bailable")]),
    ("bnss-bail-high-court", "advocate", "bail", "What are the special powers of the High Court regarding bail?", [s(BNSS, "483", "bail")]),
    ("bnss-undertrial", "advocate", "bail", "How long can an undertrial be detained before release?", [s(BNSS, "479", "half")]),
    ("bnss-bailable", "citizen", "bail", "Do I have a right to bail for a bailable offence?", [s(BNSS, "478", "bail")]),
    # ---- BSA
    ("bsa-current", "advocate", "currency", "Which law now governs evidence in criminal trials?", [{"act": BSA}]),
    ("bsa-dying-declaration", "citizen", "evidence", "Is a statement made by a dying person accepted as evidence?", [s(BSA, "26", "death")]),
    ("bsa-confession-police", "police", "evidence", "Is a confession made to a police officer admissible?", [s(BSA, "23", "confession")]),
    ("bsa-electronic", "citizen", "evidence", "How is evidence held on a phone or computer proved in court?", [s(BSA, "63", "electronic")]),
    ("bsa-certificate", "advocate", "evidence", "Is a certificate mandatory to prove an electronic record?", [s(BSA, "63", "certificate")]),
    ("bsa-expert", "citizen", "evidence", "When may a court rely on an expert's opinion?", [s(BSA, "39", "opinion")]),
    ("bsa-burden", "advocate", "evidence", "Who bears the burden of proof?", [s(BSA, "104", "burden")]),
    # ---- Special criminal statutes
    ("pocso-reporting", "police", "children", "Who must report a sexual offence against a child?", [s("sexual offences", "19", "report")]),
    ("pocso-assault", "citizen", "children", "What is sexual assault against a child under the law?", [s("sexual offences", "7", "sexual")]),
    ("sc-st-atrocity", "citizen", "protective", "What protection does the law give Scheduled Castes against atrocities?", [s("atrocities", "3", "Scheduled")]),
    ("sc-st-court", "police", "protective", "Which court tries offences under the atrocities law?", [s("atrocities", "14", "Special Court")]),
    ("arms-licence", "citizen", "regulatory", "How is a licence for a firearm obtained?", [s("arms act", "13", "licen")]),
    ("jj-child-care", "citizen", "children", "What happens to a child who needs care and protection?", [s("juvenile justice", "31", "child")]),
    ("it-identity-theft", "citizen", "cyber", "Someone used my password and OTP to pretend to be me online. Which provision applies?", [s("information technology act", "66C", "password")]),
    ("it-impersonation", "police", "cyber", "What is the offence of cheating by personation using a computer resource?", [s("information technology act", "66D", "personation")]),
    ("dowry-prohibition", "citizen", "family", "Is giving or taking dowry an offence?", [s("dowry prohibition", "3", "dowry")]),
    # ---- Civil and everyday law, untested before this set
    ("contract-valid", "citizen", "civil", "What are the essential elements of a valid contract?", [s("contract act", "10", "free consent")]),
    ("contract-breach", "advocate", "civil", "What compensation is available for breach of contract?", [s("contract act", "73", "compensation")]),
    ("consumer-complaint", "citizen", "consumer", "A shop sold defective goods and refuses a refund. What remedy exists?", [s("consumer protection act, 2019", "35", "complaint")]),
    ("consumer-forum", "citizen", "consumer", "Where do I file a consumer complaint worth a small amount?", [s("consumer protection act, 2019", "34", "District Commission")]),
    ("rti-apply", "citizen", "rights", "How do I ask a government office for information?", [s("right to information act", "6", "information")]),
    ("rti-time", "citizen", "rights", "How long does a public authority have to answer my information request?", [s("right to information act", "7", "thirty days")]),
    ("rti-appeal", "citizen", "rights", "What can I do if my information request is refused?", [s("right to information act", "19", "appeal")]),
    ("dv-residence", "citizen", "family", "Can a woman be thrown out of the shared home by her husband?", [s("domestic violence act", "17", "shared household")]),
    ("dv-protection", "citizen", "family", "What protection orders can a magistrate give for domestic violence?", [s("domestic violence act", "18", "protection order")]),
    ("posh-complaint", "citizen", "workplace", "What is the process for a sexual harassment complaint at work?", [s("sexual harassment of women at workplace", "9", "complaint")]),
    ("hma-divorce", "citizen", "family", "On what grounds can a Hindu marriage be dissolved?", [s("hindu marriage", "13", "divorce")]),
    ("hma-maintenance", "citizen", "family", "Can a spouse claim maintenance while a divorce case is running?", [s("hindu marriage", "24", "maintenance")]),
    ("mv-claim", "citizen", "civil", "How do I claim compensation after a road accident?", [s("motor vehicles act", "166", "compensation")]),
    ("mv-insurance", "citizen", "civil", "Is third party insurance compulsory for vehicles?", [s("motor vehicles act", "146", "insurance")]),
    ("ni-cheque", "citizen", "civil", "A cheque given to me has bounced. What can I do?", [s("negotiable instruments", "138", "dishonour")]),
    ("limitation-bar", "advocate", "civil", "What happens to a suit filed after the limitation period?", [s("limitation act", "3", "dismissed")]),
    ("cpc-jurisdiction", "advocate", "civil", "Which suits may civil courts try?", [s("code of civil procedure", "9", "civil nature")]),
    ("tpa-lease", "citizen", "property", "What is a lease of immovable property?", [s("transfer of property", "105", "lease")]),
    ("legal-aid", "citizen", "rights", "Can a person who cannot afford a lawyer get one free?", [s("legal services authorities", "12", "legal services")]),
    # ---- Judgments and guidance, where a document rather than a section governs
    ("case-puttaswamy", "advocate", "precedent", "What did the Supreme Court hold about privacy in Puttaswamy?", [{"title_contains": "PUTTASWAMY"}]),
    ("case-kaushal", "advocate", "precedent", "Can a minister's statement be attributed to the State?", [{"title_contains": "Kaushal"}]),
    ("case-joseph-shine", "advocate", "precedent", "What did the Supreme Court decide about adultery in Joseph Shine?", [{"title_contains": "Joseph Shine"}]),
    ("case-sita-soren", "advocate", "precedent", "Does parliamentary privilege protect a legislator who takes a bribe?", [{"title_contains": "Sita Soren"}]),
    ("case-arjun-khotkar", "advocate", "precedent", "What did Arjun Panditrao Khotkar decide about electronic evidence?", [{"title_contains": "Arjun Panditrao"}]),
    ("sop-chain-custody", "police", "guidance", "How must chain of custody be maintained for seized material?", [{"contains": "chain of custody"}]),
    ("sop-electronic-device", "police", "guidance", "How should an electronic device be seized and preserved?", [{"contains": "hash value"}]),
    ("sop-audio-video", "police", "guidance", "What is the procedure for audio-video recording of evidence?", [{"title_contains": "Audio-Video"}]),
]

# Nothing in a corpus of Indian law can answer these. Abstaining is the right answer.
MUST_ABSTAIN: list[tuple[str, str]] = [
    ("foreign-visa", "What are the visa requirements for studying in Canada?"),
    ("foreign-green-card", "How do I apply for a United States green card?"),
    ("foreign-uk-divorce", "How do I get a divorce in England?"),
    ("foreign-dubai-labour", "What notice period applies to my job in Dubai?"),
    ("off-topic-recipe", "What is a good recipe for biryani?"),
    ("off-topic-medical", "What dose of paracetamol should I give a child with fever?"),
    ("off-topic-stocks", "Which shares should I buy this month?"),
    ("off-topic-cricket", "Who won the last cricket world cup?"),
]

# Grounds written from the Acts for v3, carried across unchanged.
V3_GROUNDS = {
    "bnss-handcuff": "handcuffing",
    "bsa-dying-declaration": "dying-declaration",
    "bnss-default-bail": "default-bail",
    "bnss-anticipatory": "anticipatory-bail",
    "bnss-remand": "police-vs-judicial-custody",
    "bnss-arrest-woman": "arrest-of-woman",
    "bnss-grounds": "grounds-of-arrest",
    "bns-theft-current": "theft-current-law",
    "bnss-arrest-current": "arrest-current-law",
    "bsa-current": "evidence-current-law",
}


def main() -> int:
    rows = [json.loads(line) for line in (KB / "metadata/canonical_documents.jsonl").open(encoding="utf-8")]
    units_cache: dict[str, list] = {}

    def units_for(row: dict) -> list:
        key = row["canonical_document_id"]
        if key not in units_cache:
            path = KB / "processed/extracted_text" / f"{key}.json"
            units_cache[key] = (
                parse_legal_structure(
                    ExtractedDocument.model_validate_json(path.read_text(encoding="utf-8")),
                    LegalDocumentType.ACT,
                )
                if path.is_file()
                else []
            )
        return units_cache[key]

    def is_the_act(row: dict, act: str) -> bool:
        name = f"{row.get('act_name') or ''} {row.get('title') or ''}".casefold()
        return act in name and row.get("source_type") in {"act", "constitution", "amendment_act"}

    problems: list[str] = []
    for item_id, _, _, _, sources in ITEMS:
        for source in sources:
            if "verify" not in source:
                continue
            candidates = [row for row in rows if is_the_act(row, source["act"])]
            words = source["verify"].casefold()
            found = any(
                words in re.sub(r"\s+", " ", unit.text).casefold()
                for row in candidates
                for unit in units_for(row)
                if str(unit.section) == source["section"]
            )
            if not found:
                problems.append(
                    f"{item_id}: {source['act']} s.{source['section']} does not contain "
                    f"'{source['verify']}' ({len(candidates)} candidate documents)"
                )
        for source in sources:
            if "title_contains" in source and not any(
                source["title_contains"].casefold() in str(row.get("title") or "").casefold() for row in rows
            ):
                problems.append(f"{item_id}: no document titled '{source['title_contains']}'")

    if problems:
        print(f"{len(problems)} items are not borne out by the corpus:")
        print("\n".join(f"  {line}" for line in problems))
        if "--write-anyway" not in sys.argv:
            return 1

    v3 = {item["id"]: item for item in json.loads((KB / "evaluation/golden_set_v3.json").read_text(encoding="utf-8"))["items"]}
    items = []
    for item_id, role, topic, question, sources in ITEMS:
        entry = {
            "id": item_id,
            "question": question,
            "role": role,
            "topic": topic,
            "expectation": "answer",
            "relevant": [{k: v for k, v in source.items() if k != "verify"} for source in sources],
        }
        carried = v3.get(V3_GROUNDS.get(item_id, ""))
        if carried and carried.get("grounds"):
            entry["grounds"] = carried["grounds"]
            entry["grounds_source"] = carried.get("grounds_source", "")
        items.append(entry)
    items += [
        {"id": item_id, "question": question, "role": "citizen", "topic": "out_of_scope", "expectation": "abstain"}
        for item_id, question in MUST_ABSTAIN
    ]
    OUT.write_text(
        json.dumps(
            {
                "version": 4,
                "created": "2026-11-04",
                "notes": [
                    "Items name the Act and section that govern the question. Each is verified against that section's text by scripts/build_golden_set_v4.py.",
                    "A passage that merely mentions a provision does not count. Repealed-code equivalents do not count, since the question is what the law is.",
                    "Written from the statutes, not from retrieval output. Do not edit an item to suit a result.",
                ],
                "items": items,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    by_role: dict[str, int] = {}
    for item in items:
        by_role[item["role"]] = by_role.get(item["role"], 0) + 1
    print(f"wrote {OUT.relative_to(ROOT)}: {len(items)} items, {by_role}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
