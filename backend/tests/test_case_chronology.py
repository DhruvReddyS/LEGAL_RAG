"""Dates as the documents state them, in order, each traced to its page."""

from __future__ import annotations

from datetime import date

import pytest

from app.services.case_chronology import MAX_EVENTS, build_chronology, dates_in

LATEST = 2036


def _dates(text: str) -> list[str]:
    return [when.isoformat() for _, when, _ in dates_in(text, latest_year=LATEST)]


@pytest.mark.parametrize(
    "written, expected",
    [
        ("on 19/03/2024 at night", "2024-03-19"),
        ("on 19-03-2024", "2024-03-19"),
        ("on 19.03.2024", "2024-03-19"),
        ("on 05/03/2024", "2024-03-05"),
        ("on 19/03/24", "2024-03-19"),
        ("on 19/03/98", "1998-03-19"),
        ("on 19 March 2024", "2024-03-19"),
        ("on 19th March, 2024", "2024-03-19"),
        ("on the 19th day of March, 2024", "2024-03-19"),
        ("on March 19, 2024", "2024-03-19"),
        ("on 19 Mar 2024", "2024-03-19"),
        ("29/02/2024", "2024-02-29"),
    ],
)
def test_the_ways_dates_are_written(written, expected) -> None:
    assert _dates(written) == [expected]


@pytest.mark.parametrize(
    "written",
    [
        "31/02/2024",
        "12/13/2024",
        "29/02/2023",
        "Section 19 of the Act of 2023",
        "Crl.A. No. 19/2024",
        "FIR No. 123/2024",
        "1/2/3",
        "phone 98765-43210",
        "on 19/03/1850",
        "on 19/03/2099",
    ],
)
def test_what_is_not_a_real_date_is_left_out(written) -> None:
    assert _dates(written) == []


def test_a_month_and_year_keeps_its_precision() -> None:
    found = dates_in("The tenancy began in March 2021.", latest_year=LATEST)
    assert [(when.isoformat(), precision) for _, when, precision in found] == [("2021-03-01", "month")]


def _chunk(text: str, **fields) -> dict:
    return {"text": text, "document_id": "doc-1", "title": "FIR.pdf", "page_start": 3, "page_end": 3, **fields}


def test_events_come_out_in_date_order_across_files() -> None:
    result = build_chronology(
        [
            _chunk("The accused was arrested on 20/03/2024.", title="Arrest memo.pdf", document_id="b"),
            _chunk("The complaint was lodged on 19/03/2024."),
        ]
    )
    assert [event["date"] for event in result["events"]] == ["2024-03-19", "2024-03-20"]
    assert result["documents_read"] == 2


def test_each_event_is_the_documents_own_sentence_and_its_page() -> None:
    result = build_chronology([_chunk("Nothing here. The notice was served on 2 May 2024. Other text follows.")])
    event = result["events"][0]
    assert event["text"] == "The notice was served on 2 May 2024."
    assert (event["title"], event["page_start"]) == ("FIR.pdf", 3)


def test_a_repeated_sentence_is_one_event_but_two_dates_are_two() -> None:
    text = "He left on 1 May 2024 and returned on 3 May 2024."
    result = build_chronology([_chunk(text), _chunk(text, title="Copy.pdf", document_id="d")])
    assert [event["date"] for event in result["events"]] == ["2024-05-01", "2024-05-03"]


def test_a_long_sentence_keeps_the_date_in_view() -> None:
    text = "word " * 200 + "served on 2 May 2024 " + "word " * 200
    event = build_chronology([_chunk(text)])["events"][0]
    assert "2 May 2024" in event["text"]
    assert len(event["text"]) < 300


def test_a_future_hearing_is_kept() -> None:
    result = build_chronology([_chunk("Next hearing on 10/01/2027.")], today=date(2026, 11, 5))
    assert result["events"][0]["date"] == "2027-01-10"


def test_a_case_without_dates_is_empty_not_an_error() -> None:
    assert build_chronology([_chunk("No dates at all.")]) == {"events": [], "total_events": 0, "documents_read": 1}


def test_a_huge_file_is_capped_and_says_how_many_there_were() -> None:
    chunks = [_chunk(f"Event {n} on {1 + n % 28:02d}/{1 + n % 12:02d}/{1950 + n % 70}.") for n in range(MAX_EVENTS + 50)]
    result = build_chronology(chunks)
    assert len(result["events"]) == MAX_EVENTS
    assert result["total_events"] == MAX_EVENTS + 50
