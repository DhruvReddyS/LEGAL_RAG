"""A translation is shown only if it kept every checkable thing in the answer."""

from __future__ import annotations

import pytest

from app.services import answer_translation
from app.services.answer_translation import TranslationRejected, is_faithful, translate_answer

ANSWER = "## Direct answer\nFile within 30 days under section 138 [Source 1]. Pay 2 times the amount [Source 2]."
GOOD = "## सीधा उत्तर\nधारा 138 के तहत 30 दिनों में दाखिल करें [Source 1]। राशि का 2 गुना भुगतान करें [Source 2]।"


@pytest.mark.parametrize(
    "translated, code, expected",
    [
        (GOOD, "hi", True),
        (GOOD.replace("30", "३०").replace("138", "१३८"), "hi", True),
        (GOOD.replace("30", "60"), "hi", False),
        (GOOD.replace("138", "139"), "hi", False),
        (GOOD.replace(" [Source 2]", ""), "hi", False),
        (GOOD.replace("[Source 2]", "[Source 3]"), "hi", False),
        (ANSWER, "hi", False),
        (GOOD, "te", False),
        ("## ప్రత్యక్ష\nసెక్షన్ 138 కింద 30 రోజుల్లో [Source 1]. 2 రెట్లు [Source 2].", "te", True),
    ],
)
def test_what_counts_as_faithful(translated, code, expected) -> None:
    assert is_faithful(ANSWER, translated, code) is expected


class _Model:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls = 0
        self.prompts: list[str] = []

    async def generate_with_metrics(self, prompt, *, num_predict=900):
        self.calls += 1
        self.prompts.append(prompt)
        return self.reply, {}


@pytest.fixture(autouse=True)
def _empty_cache():
    answer_translation._cache.clear()


async def test_a_faithful_translation_is_returned_and_kept() -> None:
    model = _Model(GOOD)
    for _ in range(2):
        assert await translate_answer(model, message_id="m", answer=ANSWER, language_code="hi") == GOOD
    assert model.calls == 1
    assert "Hindi" in model.prompts[0]


async def test_an_unfaithful_one_is_refused_and_not_kept() -> None:
    model = _Model(GOOD.replace("30", "60"))
    for _ in range(2):
        with pytest.raises(TranslationRejected):
            await translate_answer(model, message_id="m", answer=ANSWER, language_code="hi")
    assert model.calls == 4


async def test_a_second_try_can_succeed() -> None:
    class _SecondTime(_Model):
        async def generate_with_metrics(self, prompt, *, num_predict=900):
            self.calls += 1
            return (GOOD.replace("30", "60") if self.calls == 1 else GOOD), {}

    model = _SecondTime(GOOD)
    assert await translate_answer(model, message_id="m", answer=ANSWER, language_code="hi") == GOOD
    assert model.calls == 2


async def test_languages_do_not_share_a_cached_translation() -> None:
    await translate_answer(_Model(GOOD), message_id="m", answer=ANSWER, language_code="hi")
    with pytest.raises(TranslationRejected):
        await translate_answer(_Model(GOOD), message_id="m", answer=ANSWER, language_code="te")
