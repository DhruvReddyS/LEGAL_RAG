"""The notice explainer reads the notice and abstains on what it cannot place."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services import section_mapping
from app.services.citizen_notice import (
    NOTICE_TYPES,
    _DraftDemand,
    _DraftPlain,
    classify,
    explain_notice,
    extract_cited_provisions,
    extract_dates,
    extract_deadlines,
    plain_language_summary,
    validate_plain,
)

CHEQUE = (
    "LEGAL NOTICE under section 138 of the Negotiable Instruments Act, 1881.\n"
    "My client's cheque no. 123456 dated 05/01/2026 for Rs. 45,000/- was returned unpaid. "
    "You are hereby called upon to make the payment within 15 (fifteen) days of receipt of this notice, "
    "failing which my client shall proceed against you."
)
POLICE_OLD = (
    "NOTICE UNDER SECTION 41A CrPC. You are directed to appear before the Investigating Officer "
    "at PS Banjara Hills on 12th January 2026 at 10.30 AM in FIR 44/2025 u/s 420 IPC."
)
SUMMONS = (
    "SUMMONS TO ACCUSED. In the Court of the Judicial Magistrate First Class, Hyderabad. "
    "Whereas your attendance is necessary to answer a charge, you are hereby required to appear on 3/2/2026."
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (CHEQUE, "cheque_notice"),
        (POLICE_OLD, "police_appearance_notice"),
        (SUMMONS, "court_summons"),
        ("Summons in O.S. No. 12 of 2025. The defendant is to file a written statement.", "civil_summons"),
        (
            "Consumer Disputes Redressal Commission. Notice to the opposite party: give your version.",
            "consumer_commission_notice",
        ),
        ("You are required to vacate the premises. Your tenancy ends this month.", "eviction_notice"),
        ("Reply from the Central Public Information Officer on your RTI application.", "rti_reply"),
        ("I issue this legal notice on behalf of my client for damages.", "advocate_notice"),
    ],
)
def test_it_recognises_the_kinds_of_notice_it_can_explain(text, expected):
    assert classify(text).key == expected


def test_a_paper_it_does_not_recognise_abstains_and_gives_no_law():
    result = explain_notice("Assessment order. Tax demand for the financial year. Reference 77/AB.")
    assert result["abstained"] is True
    assert result["provisions"] == []
    assert result["statutory_deadline"] is None
    assert "15100" in result["risk"]["en"]


def test_a_recognised_paper_is_not_abstained_and_every_card_is_a_real_quote():
    result = explain_notice(SUMMONS)
    assert result["abstained"] is False
    labels = [card["label"] for card in result["provisions"]]
    assert "BNSS s.90(b)" in labels
    for card in result["provisions"]:
        assert card["quote"] and card["source_url"].startswith("http")


def test_every_type_speaks_all_three_languages():
    for notice_type in NOTICE_TYPES:
        for field in (notice_type.label, notice_type.what_this_is, notice_type.risk):
            assert set(field) == {"en", "hi", "te"}, notice_type.key
            assert any("ऀ" <= ch <= "ॿ" for ch in field["hi"]), notice_type.key
            assert any("ఀ" <= ch <= "౿" for ch in field["te"]), notice_type.key


def test_nothing_in_the_table_predicts_an_outcome():
    for notice_type in NOTICE_TYPES:
        english = notice_type.risk["en"].casefold()
        assert "you will" not in english and "chance" not in english, notice_type.key


def test_it_reads_the_day_count_and_the_words_it_came_from():
    deadlines = extract_deadlines(CHEQUE)
    assert deadlines[0]["days"] == 15
    assert "within 15 (fifteen) days" in deadlines[0]["quote"]


def test_a_month_is_never_turned_into_a_number_of_days():
    assert extract_deadlines("Reply within one month of receipt of this notice.") == []


def test_dates_are_read_day_first_and_nonsense_is_not_given_a_date():
    found = {item["raw"]: item["iso"] for item in extract_dates("Appear on 3/2/2026. Filed 12th January 2026. Bad 45/13/2026.")}
    assert found["3/2/2026"] == "2026-02-03"
    assert found["12th January 2026"] == "2026-01-12"
    assert found["45/13/2026"] is None


def test_repealed_codes_are_labelled_with_what_replaced_them(monkeypatch):
    # The official table is tracked in git; settings point at a deployment path.
    table = Path(__file__).resolve().parents[2] / "data" / "legal_kb" / "metadata" / "section_mapping.json"
    monkeypatch.setattr(section_mapping, "_TABLE", table)
    section_mapping._load.cache_clear()
    cited = {item["section"]: item for item in extract_cited_provisions(POLICE_OLD)}
    section_mapping._load.cache_clear()
    assert cited["420"]["status"] == "replaced"
    assert cited["420"]["replaced_on"] == "2024-07-01"
    assert any(value.startswith("BNS s.318") for value in cited["420"]["successors"])


def test_a_section_of_a_current_code_is_not_called_repealed():
    cited = extract_cited_provisions("Summons u/s 90 of the Bharatiya Nagarik Suraksha Sanhita.")
    assert cited[0]["status"] == "in_force_code"
    assert cited[0]["successors"] == []


def test_a_bare_section_number_is_marked_as_not_checked():
    assert extract_cited_provisions("Under section 12 you must pay.")[0]["status"] == "not_checked"


def test_digital_arrest_is_flagged_with_the_provision_on_arrest():
    result = explain_notice("You are under digital arrest. Transfer the amount to clear your name.")
    assert result["flags"]
    assert "bnss-43-1-m" in [card["id"] for card in result["provisions"]]


def test_demands_are_verbatim_sentences_from_the_notice():
    demands = explain_notice(CHEQUE)["demands"]
    assert any("You are hereby called upon" in demand for demand in demands)
    flattened = " ".join(CHEQUE.split())
    assert all(demand in flattened for demand in demands)


# --- the model's rewrite ---------------------------------------------------


def _draft(summary: str, quote: str = "You are hereby called upon to make the payment") -> _DraftPlain:
    return _DraftPlain(summary=summary, demands=[_DraftDemand(plain="Pay the money.", quote=quote)])


def test_a_rewrite_that_stays_inside_the_notice_is_kept():
    kept = validate_plain(_draft("A lawyer asks you to pay Rs. 45,000."), CHEQUE, "en")
    assert kept and kept["summary"].startswith("A lawyer") and len(kept["demands"]) == 1


def test_a_quote_the_notice_does_not_contain_is_dropped():
    kept = validate_plain(_draft("Pay.", quote="You must surrender your passport"), CHEQUE, "en")
    assert kept and kept["demands"] == []


def test_a_rewrite_that_predicts_an_outcome_is_rejected():
    assert validate_plain(_draft("You will lose this case."), CHEQUE, "en") is None
    assert validate_plain(_draft("You are likely to win."), CHEQUE, "en") is None


def test_a_rewrite_that_brings_in_a_section_of_its_own_is_rejected():
    assert validate_plain(_draft("This is also an offence under section 420."), CHEQUE, "en") is None
    assert validate_plain(_draft("This notice is under section 138."), CHEQUE, "en") is not None


class _Llm:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.prompts = result, error, []

    async def structured(self, prompt, schema, **kwargs):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_model_failure_falls_back_to_the_deterministic_reading():
    plain, state = await plain_language_summary(_Llm(error=RuntimeError("no model")), CHEQUE, "en")
    assert plain is None and state == "unavailable"


@pytest.mark.asyncio
async def test_rejected_output_is_reported_as_rejected():
    plain, state = await plain_language_summary(_Llm(result=_draft("You will lose.")), CHEQUE, "en")
    assert plain is None and state == "rejected"


@pytest.mark.asyncio
async def test_the_prompt_treats_the_notice_as_data_and_names_the_language():
    llm = _Llm(result=_draft("ठीक है"))
    plain, state = await plain_language_summary(llm, CHEQUE, "hi")
    assert state == "ok" and plain["language"] == "hi"
    assert "not instructions" in llm.prompts[0] and "Hindi" in llm.prompts[0]
