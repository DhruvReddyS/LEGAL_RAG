"""The statutory text the advocate tools rest on, quoted and pinned to a page.

The bail and limitation calculators state law without asking a model, so what
they state has to be checkable some other way. Every entry here carries the
exact words of the provision, as a tuple of fragments that each appear
contiguously on the named page of the corpus document (the printed Acts run
marginal notes through the text, so one sentence can span two fragments).
`tests/test_advocate_provisions_match_corpus.py` reads the corpus and fails on
any fragment that is not there. A provision that cannot be pinned this way
does not belong in this file, and the tools say nothing about it.

Currency comes from `citation_labels_for`, the same call every other lane
makes, so a repeal recorded in the corpus reaches these tools too.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.citation_status import citation_labels_for

BNSS_DOC = (
    "gold-canonical-5e60e2afe30d0fe7eca4f812",
    "THE BHARATIYA NAGARIK SURAKSHA SANHITA, 2023",
    "https://www.mha.gov.in/sites/default/files/2024-04/250884_2_english_01042024.pdf",
)
LIMITATION_DOC = (
    "exp-canonical-f04b51220f8f7ec97a1d7e8c",
    "The Limitation Act, 1963",
    "https://indiacode.gov.in/server/api/core/bitstreams/3900a3de-8131-435a-9af0-ebad58242273/content",
)
CPC_DOC = (
    "exp-canonical-393b8848fdfc476a21cc3abf",
    "The Code of Civil Procedure, 1908",
    "https://indiacode.gov.in/server/api/core/bitstreams/fc9dad3f-97a9-4216-843b-934665693468/content",
)


@dataclass(frozen=True)
class Provision:
    key: str
    label: str
    document: tuple[str, str, str]
    page: int
    fragments: tuple[str, ...]
    # A second page, for a sentence that crosses a page break.
    last_page: int | None = None

    @property
    def quote(self) -> str:
        return " ".join(self.fragments)

    def as_source(self) -> dict[str, Any]:
        """The shape every advocate surface renders a source in."""
        document_id, title, source_url = self.document
        labels = citation_labels_for(
            {
                "canonical_document_id": document_id,
                "title": title,
                "act_name": title,
                "source_type": "act",
                "source_url": source_url,
            }
        )
        return {
            "point_id": f"provision:{self.key}",
            "chunk_id": f"provision:{self.key}",
            "title": title,
            "source_type": "act",
            "section": self.label,
            "page_start": self.page,
            "page_end": self.last_page or self.page,
            "excerpt": self.quote,
            "relevance_score": None,
            # Checked against the corpus page by a test, not by a model.
            "verification_status": "verified",
            "scope": "global",
            "source_url": f"{source_url}#page={self.page}",
            "document_id": document_id,
            **labels,
        }


def _p(key: str, label: str, document: tuple[str, str, str], page: int, *fragments: str, last_page: int | None = None) -> Provision:
    return Provision(key, label, document, page, tuple(fragments), last_page)


_ALL = (
    # ---- BNSS: bail
    _p("bnss_187_3", "BNSS s.187(3)", BNSS_DOC, 59,
       "no Magistrate shall authorise the detention of the accused person in custody under this",
       "sub-section for a total period exceeding—"),
    _p("bnss_187_3_i", "BNSS s.187(3)(i)", BNSS_DOC, 60,
       "(i) ninety days, where the investigation relates to an offence punishable with death, imprisonment for life or imprisonment for a term of ten years or more;"),
    _p("bnss_187_3_ii", "BNSS s.187(3)(ii)", BNSS_DOC, 60,
       "(ii) sixty days, where the investigation relates to any other offence,"),
    _p("bnss_187_3_release", "BNSS s.187(3)", BNSS_DOC, 60,
       "on the expiry of the said period of ninety days, or sixty days, as the case may be, the accused person shall be released on bail if he is prepared to and does furnish bail"),
    _p("bnss_187_expl_1", "BNSS s.187, Explanation I", BNSS_DOC, 60,
       "notwithstanding the expiry of the period specified in sub-section (3), the accused shall be detained in custody so long as he does not furnish bail."),
    _p("bnss_478_1", "BNSS s.478(1)", BNSS_DOC, 144,
       "is prepared at any time while in the custody of such officer or at any stage of the proceeding before such Court to give bail, such person shall be released on bail"),
    _p("bnss_479_1", "BNSS s.479(1)", BNSS_DOC, 144,
       "(not being an offence for which the punishment of death or life imprisonment has been specified as one of the punishments under that law) undergone detention for a period extending up to one-half of the maximum period of imprisonment specified for that offence under that law, he shall be released by the Court on bail"),
    _p("bnss_479_first_time", "BNSS s.479(1), first proviso", BNSS_DOC, 144,
       "Provided that where such person is a first-time offender (who has never been convicted of any offence in the past) he shall be released on bond by the Court, if he has undergone detention for the period extending up to one-third of the maximum period of imprisonment specified for such offence under that law"),
    _p("bnss_479_continued", "BNSS s.479(1), second proviso", BNSS_DOC, 144,
       "the Court may, after hearing the Public Prosecutor and for reasons to be recorded by it in writing, order the continued detention of such person for a period longer than one-half of the said period or release him on bail bond instead of his bond"),
    _p("bnss_479_maximum", "BNSS s.479(1), third proviso", BNSS_DOC, 144,
       "no such person shall in any case be detained during the period of investigation, inquiry or trial for more than the maximum period of imprisonment provided for the said offence under that law."),
    _p("bnss_479_explanation", "BNSS s.479, Explanation", BNSS_DOC, 144,
       "In computing the period of detention under this section for granting bail, the period of detention passed due to delay in proceeding caused by the accused shall be excluded."),
    _p("bnss_479_2", "BNSS s.479(2)", BNSS_DOC, 144,
       "where an investigation, inquiry or trial in more than one offence or in multiple cases are pending against a person, he shall not be released on bail by the Court."),
    _p("bnss_479_3", "BNSS s.479(3)", BNSS_DOC, 144,
       "The Superintendent of jail, where the accused person is detained, on completion of one-half or one-third of the period mentioned in sub-section (1), as the case may be, shall forthwith make an application in writing to the Court"),
    _p("bnss_480_1", "BNSS s.480(1)", BNSS_DOC, 144,
       "or appears or is brought before a Court other than the High Court or Court of Session, he may be released on bail, but—"),
    _p("bnss_480_1_i", "BNSS s.480(1)(i)", BNSS_DOC, 144,
       "(i) such person shall not be so released if there appear reasonable grounds for",
       "believing that he has been guilty of an offence punishable with death or imprisonment for life;", last_page=145),
    _p("bnss_480_1_ii", "BNSS s.480(1)(ii)", BNSS_DOC, 145,
       "(ii) such person shall not be so released if such offence is a cognizable offence and he had been previously convicted of an offence punishable with death, imprisonment for life or imprisonment for seven years or more, or he had been previously convicted on two or more occasions of a cognizable offence punishable with imprisonment for three years or more but less than seven years"),
    _p("bnss_480_child_woman", "BNSS s.480(1), first proviso", BNSS_DOC, 145,
       "Provided that the Court may direct that a person referred to in clause (i) or clause (ii) be released on bail if such person is a child or is a woman or is sick or infirm"),
    _p("bnss_480_prosecutor", "BNSS s.480(1), fourth proviso", BNSS_DOC, 145,
       "no person shall, if the offence alleged to have been committed by him is punishable with death, imprisonment for life, or imprisonment for seven years or more, be released on bail by the Court under this sub-section without giving an opportunity of hearing to the Public Prosecutor."),
    _p("bnss_480_3", "BNSS s.480(3)", BNSS_DOC, 145,
       "When a person accused or suspected of the commission of an offence punishable with imprisonment which may extend to seven years or more or of an offence under Chapter VI, Chapter VII or Chapter XVII of the Bharatiya Nyaya Sanhita, 2023 or abetment of, or conspiracy or attempt to commit, any such offence, is released on bail under sub-section (1), the Court shall impose the conditions,—"),
    _p("bnss_480_6", "BNSS s.480(6)", BNSS_DOC, 146,
       "If, in any case triable by a Magistrate, the trial of a person accused of any non-bailable offence is not concluded within a period of sixty days from the first date fixed for taking evidence in the case, such person shall, if he is in custody during the whole of the said period, be released on bail to the satisfaction of the Magistrate, unless for reasons to be recorded in writing, the Magistrate otherwise directs."),
    _p("bnss_482_1", "BNSS s.482(1)", BNSS_DOC, 146,
       "When any person has reason to believe that he may be arrested on an accusation of having committed a non-bailable offence, he may apply to the High Court or the Court of Session for a direction under this section; and that Court may, if it thinks fit, direct that in the event of such arrest, he shall be released on bail."),
    _p("bnss_482_2", "BNSS s.482(2)", BNSS_DOC, 146,
       "(i) a condition that the person shall make himself available for interrogation by a police officer as and when required;",
       "(iii) a condition that the person shall not leave India without the previous permission of the Court;"),
    _p("bnss_482_4", "BNSS s.482(4)", BNSS_DOC, 146,
       "Nothing in this section shall apply to any case involving the arrest of any person on accusation of having committed an offence under section 65 and sub-section (2) of section 70 of the Bharatiya Nyaya Sanhita, 2023."),
    _p("bnss_483_1", "BNSS s.483(1)(a)", BNSS_DOC, 146,
       "A High Court or Court of Session may direct,—",
       "(a) that any person accused of an offence and in custody be released on bail,"),
    _p("bnss_483_notice", "BNSS s.483(1), first proviso", BNSS_DOC, 147,
       "Provided that the High Court or the Court of Session shall, before granting bail to a person who is accused of an offence which is triable exclusively by the Court of Session or which, though not so triable, is punishable with imprisonment for life, give notice of the application for bail to the Public Prosecutor"),
    _p("bnss_531_2_a", "BNSS s.531(2)(a)", BNSS_DOC, 156,
       "(a) if, immediately before the date on which this Sanhita comes into force, there is any appeal, application, trial, inquiry or investigation pending, then, such appeal, application, trial, inquiry or investigation shall be disposed of, continued, held or",
       "Procedure, 1973, as in force immediately before such commencement", last_page=157),
    # ---- BNSS: discharge and quashing
    _p("bnss_250_1", "BNSS s.250(1)", BNSS_DOC, 82,
       "The accused may prefer an application for discharge within a period of sixty days from the date of commitment of the case under section 232."),
    _p("bnss_250_2", "BNSS s.250(2)", BNSS_DOC, 82,
       "the Judge considers that there is not sufficient ground for proceeding against the accused, he shall discharge the accused and record his reasons for so doing."),
    _p("bnss_262_1", "BNSS s.262(1)", BNSS_DOC, 84,
       "The accused may prefer an application for discharge within a period of sixty",
       "days from the date of supply of copies of documents under section 230."),
    _p("bnss_262_2", "BNSS s.262(2)", BNSS_DOC, 84,
       "charge against the accused to be groundless, he shall discharge the accused, and record his reasons for so doing."),
    _p("bnss_528", "BNSS s.528", BNSS_DOC, 156,
       "Nothing in this Sanhita shall be deemed to limit or affect the inherent powers of",
       "the High Court to make such orders as may be necessary to give effect to any order under",
       "this Sanhita, or to prevent abuse of the process of any Court or otherwise to secure the",
       "ends of justice."),
    # ---- Limitation Act: the sections that govern the arithmetic
    _p("lim_3_1", "Limitation Act s.3(1)", LIMITATION_DOC, 4,
       "every suit instituted, appeal preferred, and application made after the prescribed period shall be dismissed, although limitation has not been set up as a defence."),
    _p("lim_4", "Limitation Act s.4", LIMITATION_DOC, 4,
       "Where the prescribed period for any suit, appeal or application expires on a day when the court is closed, the suit, appeal or application may be instituted, preferred or made on the day when the court re-opens."),
    _p("lim_5", "Limitation Act s.5", LIMITATION_DOC, 4,
       "may be admitted after the prescribed period if the appellant or the applicant satisfies the court that he had sufficient cause for not preferring the appeal or making the application within such period."),
    _p("lim_12_1", "Limitation Act s.12(1)", LIMITATION_DOC, 6,
       "In computing the period of limitation for any suit, appeal or application, the day from which such period is to be reckoned, shall be excluded."),
    _p("lim_12_2", "Limitation Act s.12(2)", LIMITATION_DOC, 6,
       "the day on which the judgment complained of was pronounced and the time requisite for obtaining a copy of the decree, sentence or order appealed from or sought to be revised or reviewed shall be excluded."),
    # ---- Limitation Act: Schedule articles
    _p("lim_art_54", "Limitation Act, Schedule, Art. 54", LIMITATION_DOC, 15,
       "For specific performance of a Three years. The date fixed for the performance, or, if contract. no such date is fixed, when the plaintiff has notice that performance is refused."),
    _p("lim_art_55", "Limitation Act, Schedule, Art. 55", LIMITATION_DOC, 15,
       "For compensation for the breach of Three years. When the contract is broken or (where"),
    _p("lim_art_58", "Limitation Act, Schedule, Art. 58", LIMITATION_DOC, 16,
       "To obtain any other declaration. Three years. When the right to sue first accrues."),
    _p("lim_art_59", "Limitation Act, Schedule, Art. 59", LIMITATION_DOC, 16,
       "To cancel or set aside an instrument Three years. When the facts entitling the plaintiff to"),
    _p("lim_art_65", "Limitation Act, Schedule, Art. 65", LIMITATION_DOC, 17,
       "For possession of immovable Twelve years. When the possession of the defendant property or any interest therein becomes adverse to the plaintiff."),
    _p("lim_art_113", "Limitation Act, Schedule, Art. 113", LIMITATION_DOC, 21,
       "Any suit for which no period of Three years. When the right to sue accrues. limitation is provided elsewhere in this Schedule."),
    _p("lim_art_114_a", "Limitation Act, Schedule, Art. 114(a)", LIMITATION_DOC, 21,
       "Ninety days. The date of the order appealed from."),
    _p("lim_art_114_b", "Limitation Act, Schedule, Art. 114(b)", LIMITATION_DOC, 21,
       "Thirty days. The date of the grant of special leave."),
    _p("lim_art_115_a", "Limitation Act, Schedule, Art. 115(a)", LIMITATION_DOC, 22,
       "(a) from a sentence of death Thirty days. The date of the sentence."),
    _p("lim_art_115_b_i", "Limitation Act, Schedule, Art. 115(b)(i)", LIMITATION_DOC, 22,
       "(i) to the High Court Sixty days. The date of the sentence or order."),
    _p("lim_art_115_b_ii", "Limitation Act, Schedule, Art. 115(b)(ii)", LIMITATION_DOC, 22,
       "(ii) to any other court Thirty days. The date of the sentence or order."),
    _p("lim_art_116_a", "Limitation Act, Schedule, Art. 116(a)", LIMITATION_DOC, 22,
       "(a) to a High Court from any Ninety days. The date of the decree or order."),
    _p("lim_art_116_b", "Limitation Act, Schedule, Art. 116(b)", LIMITATION_DOC, 22,
       "(b) to any other court from any Thirty days. The date of the decree or order."),
    _p("lim_art_117", "Limitation Act, Schedule, Art. 117", LIMITATION_DOC, 22,
       "From a decree or order of any High Thirty days. The date of the decree or order. Court to the same Court."),
    _p("lim_art_118", "Limitation Act, Schedule, Art. 118", LIMITATION_DOC, 22,
       "For leave to appear and defend a Ten days. When the summons is served."),
    _p("lim_art_123", "Limitation Act, Schedule, Art. 123", LIMITATION_DOC, 23,
       "To set aside a decree passed ex The date of the decree or where the",
       "Thirty days. parte or to rehear an appeal summons or notice was not duly"),
    _p("lim_art_124", "Limitation Act, Schedule, Art. 124", LIMITATION_DOC, 23,
       "For a review of judgment by a Thirty days. The date of the decree or order. court other than the Supreme Court."),
    _p("lim_art_131", "Limitation Act, Schedule, Art. 131", LIMITATION_DOC, 23,
       "To any court for the exercise of Ninety days. The date of the decree or order or its powers of revision under sentence sought to be revised."),
    _p("lim_art_137", "Limitation Act, Schedule, Art. 137", LIMITATION_DOC, 24,
       "Any other application for which Three years. When the right to apply accrues. no period of limitation is provided elsewhere in this Division."),
    # ---- CPC
    _p("cpc_order_3_rule_4", "CPC, Order III, rule 4(1)", CPC_DOC, 90,
       "No pleader shall act for any person in any Court, unless he has been",
       "appointed for the purpose by such person by a document in writing signed by such person or by his recognized"),
    _p("cpc_80", "CPC s.80(1)", CPC_DOC, 61,
       "until the expiration of two months next after notice in writing has been"),
)

PROVISIONS: dict[str, Provision] = {item.key: item for item in _ALL}


def provision_sources(*keys: str) -> list[dict[str, Any]]:
    return [PROVISIONS[key].as_source() for key in keys]
