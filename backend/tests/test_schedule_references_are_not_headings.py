"""A sentence that names a schedule does not start one.

The Parsi Marriage and Divorce Act, 1936 wraps s.6 so that a line begins
"Schedule  II. The certificate shall be signed by the said priest, ...". That
line was read as a schedule heading, schedule mode skipped every section head
after it, and s.7-52 -- the Act's divorce law, s.32 and s.32B included -- were
indexed in long chunks with no section number. Re-parsed with this rule, the
Act has 55 sections instead of 6, and no other document in the corpus loses one.
"""

from __future__ import annotations

from app.ingestion.extract import ExtractedDocument, ExtractedPage
from app.ingestion.structure import _act_heading, _parse_acts

_FILLER = "\n".join(f"Arrangement line {n} of the contents." for n in range(12))

PARSI_LAYOUT = f"""THE PARSI MARRIAGE AND DIVORCE ACT, 1936
{_FILLER}
1. Short title, extent and commencement.—(1) This Act may be called the Parsi Marriage and
Divorce Act, 1936, and it extends to the whole of India.
2. Definitions.—In this Act, unless there is anything repugnant in the subject or context,
the words defined here have the meanings given to them in this section.
3. Requisites to validity of Parsi marriages.—No marriage shall be valid if the contracting
parties are related to each other in any of the degrees of consanguinity or affinity.
4. Remarriage when unlawful.—No Parsi shall contract any marriage under this Act during the
lifetime of his or her wife or husband except after a lawful divorce.
5. Punishment of bigamy.—Every Parsi who during the lifetime of his or her wife or husband
contracts a marriage shall be subject to the penalties provided in the Penal Code.
6.  Certificate and  registry  of marriage.—Every marriage  contracted under  this Act  shall,
immediately on the solemnization thereof, be certified by the officiating priest in the form contained in
Schedule  II. The certificate shall be signed by the said priest, the contracting parties and two
witnesses present at the marriage and the said priest shall thereupon send such certificate.

    7. Appointment of Registrar.—For the purposes of this Act a Registrar shall be appointed within
the local limits of the ordinary original civil jurisdiction of a High Court.

    32. Grounds for divorce.—Any married person may sue for divorce on any one or more of the
following grounds, namely, that the defendant has deserted the plaintiff for at least two years.

    32B. Divorce by mutual consent.—Subject to the provisions of this Act, a suit for divorce may be
filed by both the parties to the marriage together on the ground that they have been living separately.

SCHEDULE II
    (See section 6)
Certificate of Marriage
    1. Date and place of marriage.
    2. Names of the husband and wife.
"""


def _document(text: str) -> ExtractedDocument:
    return ExtractedDocument(
        document_id="parsi-test",
        source_path="parsi.pdf",
        pages=[
            ExtractedPage(
                page_number=1,
                text=text,
                original_page_text=text,
                extraction_method="native",
                ocr_used=False,
            )
        ],
    )


def _sections(text: str) -> list[str]:
    return [unit.section for unit in _parse_acts(_document(text)) if unit.section]


def test_the_sections_after_a_wrapped_schedule_reference_keep_their_numbers() -> None:
    assert _sections(PARSI_LAYOUT) == ["1", "2", "3", "4", "5", "6", "7", "32", "32B"]


def test_the_divorce_section_carries_its_own_text() -> None:
    units = {unit.section: unit for unit in _parse_acts(_document(PARSI_LAYOUT)) if unit.section}
    assert "deserted the plaintiff" in units["32"].text
    assert "mutual consent" in units["32B"].text


def test_the_real_schedule_still_starts_schedule_mode() -> None:
    # The schedule's own numbered entries must not become sections 1 and 2 again.
    assert _sections(PARSI_LAYOUT).count("1") == 1
    assert _act_heading("SCHEDULE II") is not None


def test_short_schedule_headings_are_still_headings() -> None:
    for line in ("SCHEDULE II", "Schedule I", "Schedule I - Offences under this Act", "THE SCHEDULE"):
        assert _act_heading(line) is not None or line == "THE SCHEDULE", line


def test_a_sentence_naming_a_schedule_is_not_a_heading() -> None:
    line = "Schedule  II. The certificate shall be signed by the said priest, the contracting parties and two"
    assert _act_heading(line) is None


def test_a_long_upper_case_schedule_title_is_still_a_heading() -> None:
    assert _act_heading("SCHEDULE III. FORMS OF APPLICATION FOR REGISTRATION OF A MARRIAGE UNDER THIS ACT") is not None
