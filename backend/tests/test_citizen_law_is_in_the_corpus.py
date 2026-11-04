"""A provision written into citizen content has to say what we claim it says.

Rights, the forum router, the journeys, legal aid, drafts and the notice
explainer all rest on one ledger of provisions, each with a short verbatim
quote. Nothing else proves those words are in the law, so this reads them
against the corpus text. A renumbering or a wrong number fails here, not in
front of a person who has just been arrested.

The text is not in git. Where it is absent the corpus half skips, and the
ledger's own shape is still checked.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path

import pytest

BACKEND_LEDGER = Path(__file__).resolve().parents[1] / "app" / "services" / "citizen_provisions.json"
FRONTEND_LEDGER = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "citizen-law" / "provisions.json"


def _corpus_root() -> Path | None:
    override = os.environ.get("CITIZEN_LAW_CORPUS_ROOT")
    candidates = [Path(override)] if override else []
    # A worktree has no corpus of its own; the checkout it hangs off does.
    candidates += [parent / "data" / "legal_kb" for parent in Path(__file__).resolve().parents]
    for candidate in candidates:
        if (candidate / "processed" / "extracted_text").is_dir():
            return candidate
    return None


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    for curly, straight in (("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'), ("‐", "-")):
        text = text.replace(curly, straight)
    text = re.sub(r"_{2,}", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


LEDGER = json.loads(BACKEND_LEDGER.read_text(encoding="utf-8"))


def test_the_backend_and_frontend_ledgers_are_the_same_file():
    assert json.loads(FRONTEND_LEDGER.read_text(encoding="utf-8")) == LEDGER


def test_every_provision_names_a_known_act_and_a_real_quote():
    assert len(LEDGER["provisions"]) >= 140
    for provision_id, entry in LEDGER["provisions"].items():
        assert entry["act"] in LEDGER["acts"], provision_id
        assert entry["section"], provision_id
        assert len(entry["quote"]) >= 8, provision_id


def test_every_act_carries_an_official_source_link():
    for key, act in LEDGER["acts"].items():
        assert act["source_url"].startswith("https://") or act["source_url"].startswith("http://"), key
        assert act["document_id"], key


def test_no_cited_act_is_marked_repealed_in_the_manifest():
    root = _corpus_root()
    if root is None:
        pytest.skip("corpus text not available in this checkout")
    by_id = {}
    for line in (root / "metadata" / "canonical_documents.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        by_id[row["document_id"]] = row
        by_id[row["canonical_document_id"]] = row
    for key, act in LEDGER["acts"].items():
        row = by_id[act["document_id"]]
        assert not str(row.get("current_status", "")).startswith(("superseded", "repealed")), key


def test_every_quote_is_verbatim_in_its_document():
    root = _corpus_root()
    if root is None:
        pytest.skip("corpus text not available in this checkout")
    manifest = {}
    for line in (root / "metadata" / "canonical_documents.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        manifest[row["document_id"]] = row["canonical_document_id"]
        manifest[row["canonical_document_id"]] = row["canonical_document_id"]
    cache: dict[str, str] = {}
    missing = []
    for provision_id, entry in LEDGER["provisions"].items():
        canonical = manifest[LEDGER["acts"][entry["act"]]["document_id"]]
        if canonical not in cache:
            data = json.loads((root / "processed" / "extracted_text" / f"{canonical}.json").read_text(encoding="utf-8"))
            pages = data["pages"] if isinstance(data, dict) else data
            cache[canonical] = _normalise(" ".join(page.get("text", "") for page in pages))
        if _normalise(entry["quote"]) not in cache[canonical]:
            missing.append(provision_id)
    assert missing == []


def test_the_notice_table_only_cites_the_ledger():
    from app.services.citizen_notice import NOTICE_TYPES

    for notice_type in NOTICE_TYPES:
        assert notice_type.provisions, notice_type.key
        for provision_id in notice_type.provisions:
            assert provision_id in LEDGER["provisions"], f"{notice_type.key}: {provision_id}"
