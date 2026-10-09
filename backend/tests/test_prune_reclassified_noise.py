from __future__ import annotations

from scripts.prune_reclassified_noise import reclassified_reason


def test_only_newly_rejected_indexed_payloads_are_candidates() -> None:
    payload = {
        "quality": "indexed",
        "section": "4",
        "text": "4. Address Telephone Mobile No. E-mail",
    }
    assert reclassified_reason(payload) == "numbered_form_field"


def test_a_real_provision_is_never_a_prune_candidate() -> None:
    payload = {
        "quality": "indexed",
        "section": "4",
        "text": "4. This Act shall come into force at once.",
    }
    assert reclassified_reason(payload) is None


def test_a_point_already_marked_noise_is_not_reconsidered() -> None:
    payload = {
        "quality": "noise",
        "section": "4",
        "text": "4. Address Telephone Mobile No. E-mail",
    }
    assert reclassified_reason(payload) is None
