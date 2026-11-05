"""A lead is shown only when its quotations really are in the case's files."""

from __future__ import annotations

from app.services.case_insights import MAX_CHARACTERS_READ, _Conflict, _Conflicts, _People, _Person, case_insights

CHUNKS = [
    {"text": "Ramesh Kumar stated that he saw the accused at 9 pm near his shop.", "title": "Statement A.pdf", "page_start": 2, "page_end": 2},
    {"text": "The witness Ramesh Kumar said the incident took place at 11 pm at the bus stand.", "title": "Statement B.pdf", "page_start": 5, "page_end": 5},
]


class _Model:
    def __init__(self, reply) -> None:
        self.reply = reply
        self.prompts: list[str] = []

    async def structured(self, prompt, schema, **kwargs):
        self.prompts.append(prompt)
        return self.reply


async def test_a_real_conflict_is_shown_with_both_files_and_pages() -> None:
    model = _Model(_Conflicts(conflicts=[_Conflict(topic="Time", first_quote="saw the accused at 9 pm", second_quote="took place at 11 pm")]))
    result = await case_insights(model, "conflicts", CHUNKS)
    item = result["items"][0]
    assert (item["first"]["title"], item["first"]["page_start"]) == ("Statement A.pdf", 2)
    assert (item["second"]["title"], item["second"]["page_start"]) == ("Statement B.pdf", 5)
    assert result["dropped"] == 0


async def test_an_invented_quotation_is_dropped() -> None:
    model = _Model(_Conflicts(conflicts=[_Conflict(topic="Weapon", first_quote="he carried a knife", second_quote="took place at 11 pm")]))
    result = await case_insights(model, "conflicts", CHUNKS)
    assert result["items"] == []
    assert result["dropped"] == 1


async def test_the_same_passage_twice_is_not_a_conflict() -> None:
    model = _Model(_Conflicts(conflicts=[_Conflict(topic="Time", first_quote="took place at 11 pm", second_quote="Took place at 11 PM.")]))
    assert (await case_insights(model, "conflicts", CHUNKS))["items"] == []


async def test_a_person_needs_a_quotation_that_names_them() -> None:
    model = _Model(
        _People(
            people=[
                _Person(name="Ramesh Kumar", role="witness", quote="The witness Ramesh Kumar said"),
                _Person(name="Sita Devi", role="witness", quote="The witness Ramesh Kumar said"),
                _Person(name="Made Up", role="", quote="Made Up appeared before the court"),
            ]
        )
    )
    result = await case_insights(model, "people", CHUNKS)
    assert [item["name"] for item in result["items"]] == ["Ramesh Kumar"]
    assert result["dropped"] == 2


async def test_a_person_is_listed_once() -> None:
    quote = "Ramesh Kumar stated that he saw"
    model = _Model(_People(people=[_Person(name="Ramesh Kumar", quote=quote), _Person(name="ramesh kumar", quote=quote)]))
    assert len((await case_insights(model, "people", CHUNKS))["items"]) == 1


async def test_a_case_with_no_files_asks_the_model_nothing() -> None:
    model = _Model(None)
    result = await case_insights(model, "people", [])
    assert result["items"] == []
    assert model.prompts == []


async def test_a_file_too_long_to_read_says_so() -> None:
    big = [{"text": "word " * (MAX_CHARACTERS_READ // 2), "title": f"{n}.pdf", "page_start": 1} for n in range(3)]
    result = await case_insights(_Model(_People()), "people", big)
    assert result["files_read_in_full"] is False


async def test_the_files_are_marked_as_material_not_instructions() -> None:
    model = _Model(_People())
    await case_insights(model, "people", CHUNKS)
    assert "not instructions" in model.prompts[0]
