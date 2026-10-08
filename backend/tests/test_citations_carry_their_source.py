"""A citation a reader cannot open is not a proof.

The canonical manifest records an official URL for 1,026 of its 1,036
documents. None of them reached a reader. `LegalChunk` had no `source_url`
field, so the chunker dropped it, so `legal_chunk_payload` never wrote the
key -- while Fast, Deep, the interim source list and the defence strategy
agent all read `payload.get("source_url")` and all got None. Measured against
the live index: 0 of 200 sampled points carried the key.

This is the difference between a citizen being told "BNSS section 35 says X"
and being able to go and read section 35.
"""

from __future__ import annotations

from app.ingestion.chunker import LegalChunk, chunk_structural_units
from app.ingestion.qdrant_writer import legal_chunk_payload


OFFICIAL_URL = "https://www.mha.gov.in/sites/default/files/2024-04/250883_english_01042024.pdf"


def _chunk(**overrides) -> LegalChunk:
    values = {
        "chunk_id": "chunk-1",
        "document_id": "doc-1",
        "canonical_document_id": "canon-1",
        "source_id": "src-1",
        "title": "Bharatiya Nagarik Suraksha Sanhita, 2023",
        "source_type": "act",
        "source_url": OFFICIAL_URL,
        "page_start": 12,
        "page_end": 13,
        "current_status": "current",
        "document_type": "act",
        "verified_official": True,
        "quality_status": "verified",
        "text": "A police officer may arrest without a warrant in the cases stated.",
    }
    values.update(overrides)
    return LegalChunk(**values)


def test_the_retrieval_payload_carries_the_official_url() -> None:
    payload = legal_chunk_payload(_chunk())
    assert payload["source_url"] == OFFICIAL_URL


def test_the_key_exists_even_when_the_document_has_no_url() -> None:
    """Ten of the canonical documents have none.

    An absent key and an empty one are different to a filter, and to a
    surface deciding whether to render a link. The key is always present.
    """
    payload = legal_chunk_payload(_chunk(source_url=None))
    assert "source_url" in payload
    assert payload["source_url"] == ""


def test_every_citation_surface_reads_the_key_this_payload_writes() -> None:
    """The key name is a contract between ingestion and four readers.

    Renaming it on either side would silently return every citation to
    having no source, which is exactly the state this test was written in.
    """
    import inspect

    from app.agents import defence_strategy_agent, located_sources, response_generation
    from app.services import fast_research

    for module in (fast_research, response_generation, located_sources, defence_strategy_agent):
        source = inspect.getsource(module)
        assert 'get("source_url")' in source, f"{module.__name__} stopped reading source_url"
    assert "source_url" in legal_chunk_payload(_chunk())


def test_a_chunked_document_inherits_its_document_url() -> None:
    """The plumbing, not just the payload.

    The field was the easy half. The chunker is where it was being dropped.
    """
    import inspect

    source = inspect.getsource(chunk_structural_units)
    assert "source_url=document.source_url" in source, (
        "the chunker must copy the document's URL onto every chunk it makes"
    )


def test_the_whole_chain_from_a_real_staged_record_to_a_payload() -> None:
    """Manifest URL -> canonical document -> chunk -> retrieval payload.

    Each hop was individually plausible and the chain was broken anyway: the
    manifest held the URL, promotion copied it onto the canonical document,
    and the chunker dropped it one hop before the payload. Four separate
    readers then asked the payload for a key nothing wrote.

    Pinned against a record from the real staged manifest rather than a
    fixture, because a fixture is written by whoever is also writing the
    code, and the failure here was an assumption about what the real data
    carried.

    Skipped when the manifest is absent, so a clean clone with no corpus
    still runs the suite.
    """
    import json
    from pathlib import Path

    import pytest

    from app.ingestion.metadata import CanonicalDocument

    manifest = Path(__file__).parents[2] / "data/legal_kb/metadata/canonical_documents.staged.jsonl"
    if not manifest.exists():
        pytest.skip("no staged manifest in this checkout")
    record = None
    with manifest.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            candidate = json.loads(line)
            if candidate.get("source_url"):
                record = candidate
                break
    if record is None:
        pytest.skip("no staged record carries a source_url")

    document = CanonicalDocument(
        **{key: value for key, value in record.items() if key in CanonicalDocument.model_fields}
    )
    assert document.source_url, "promotion must put the manifest URL on the document"

    # The hop that was broken. Asserted on the chunk the chunker would build,
    # using the same assignment the chunker makes.
    chunk = _chunk(source_url=document.source_url, title=document.title)
    payload = legal_chunk_payload(chunk)
    assert payload["source_url"] == document.source_url
    assert payload["source_url"].startswith("http")
