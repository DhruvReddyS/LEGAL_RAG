from app.services.legal_term_normalization import normalize_legal_terms


def test_transposed_known_act_acronym_is_normalized() -> None:
    result = normalize_legal_terms("how to file a pocos case?")

    assert result.normalized == "how to file a POCSO case?"
    assert result.corrections == (("pocos", "POCSO"),)


def test_correct_known_act_acronym_is_unchanged() -> None:
    result = normalize_legal_terms("how to file a pocso case")

    assert result.normalized == "how to file a pocso case"
    assert result.corrections == ()


def test_unsupported_ordinary_query_is_not_rewritten() -> None:
    query = "What licensing rules apply to teleportation booths on Mars?"

    result = normalize_legal_terms(query)

    assert result.normalized == query
    assert result.corrections == ()


import pytest as _pytest


@_pytest.mark.parametrize(
    "query",
    [
        "my boss is harassing me",
        "bus accident compensation",
        "IPS officer complaint",
        "IBC insolvency petition",
        "NSA detention rights",
        "NPS pension",
        "a pic of my daughter",
        "visa to USA",
    ],
)
def test_ordinary_words_and_other_acronyms_are_left_alone(query: str) -> None:
    assert normalize_legal_terms(query).normalized == query
