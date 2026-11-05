"""CORP-05: the watch list, the offline check, the optional fetch, and the console.

Everything runs on temporary files with invented Act names. The check reads the
manifest it is pointed at and writes only under its output root.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import urllib.error
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.services import amendment_watch, currency
from main import app
from tests.helpers import provision_test_user, unique_email

PASSWORD = "Original-Password-1234"
NOW = datetime(2026, 11, 5, tzinfo=timezone.utc)


def _row(title: str, *, source_type: str = "act", **extra) -> dict:
    checksum = hashlib.sha256(title.encode()).hexdigest()
    return {
        "act_name": title,
        "canonical_document_id": f"test-canonical-{checksum[:24]}",
        "category": "primary_law/test",
        "current_status": "current/verify",
        "document_id": f"test-doc-{checksum[:24]}",
        "file_size": 1,
        "local_path": "raw/x.pdf",
        "original_filename": f"{checksum[:10]}.pdf",
        "page_count": 1,
        "quality_status": "verified",
        "sha256": checksum,
        "source_id": "x",
        "source_type": source_type,
        "source_url": f"https://acts.example.gov.in/{checksum[:10]}.pdf",
        "title": title,
        "verified_official": True,
        **extra,
    }


def _source(row: dict, **extra) -> dict:
    return {
        "id": row["document_id"],
        "title": row["title"],
        "url": row["source_url"],
        "filename": row["original_filename"],
        "current_as_of": "2026-10-03",
        "legal_status": "CURRENT_REVIEW_REQUIRED",
        **extra,
    }


class World:
    def __init__(self, root: Path) -> None:
        self.root = root / "kb"
        self.sources = root / "sources"
        self.candidates = root / "candidates"
        (self.root / "metadata").mkdir(parents=True)
        self.sources.mkdir()
        self.candidates.mkdir()
        self.table = self.root / "metadata/currency_status.json"
        self.table.write_text(
            json.dumps(
                {
                    "reviewed_on": "2026-10-01",
                    "entries": [
                        {
                            "starts_with": "the invented old code",
                            "status": "superseded",
                            "superseded_by": "The Invented New Code, 2030",
                            "basis": "Invented.",
                        },
                        {"starts_with": "the invented new code", "status": "in_force", "basis": "Invented."},
                    ],
                }
            )
        )
        self.old = _row("The Invented Old Code, 1900")
        self.new = _row("The Invented New Code, 2030")
        self.amending = _row("The Invented Tax (Amendment) Act, 2020")
        self.verify = _row(
            "The Invented Forest Act, 1950",
            currency_note="Official text; verify subsequent amendments before relying on it.",
        )
        self.ordinary = _row("The Invented Quiet Act, 1960", currency_note="India Code does not mark it repealed.")
        self.rule = _row("The Invented Tax (Amendment) Rules, 2021", source_type="rule")
        self.rows = [self.old, self.new, self.amending, self.verify, self.ordinary, self.rule]
        self.write_manifest()
        self.write_sources([_source(self.old), _source(self.new), _source(self.verify)])

    def write_manifest(self) -> None:
        (self.root / "metadata/canonical_documents.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in self.rows)
        )

    def write_sources(self, rows: list[dict]) -> None:
        (self.sources / "list.json").write_text(json.dumps(rows))

    def check(self, **options):
        options.setdefault("now", NOW)
        return amendment_watch.run_check(
            self.root, self.sources, candidates_dir=self.candidates, **options
        )


@pytest.fixture
def world(tmp_path, monkeypatch):
    built = World(tmp_path)
    monkeypatch.setattr(currency, "_DEFAULT_TABLE", built.table)
    currency._entries.cache_clear()
    yield built
    monkeypatch.undo()
    currency._entries.cache_clear()


def _kinds(report: dict) -> list[str]:
    return sorted(item["kind"] for item in report["findings"])


def _watched(report: dict) -> dict[str, dict]:
    return {item["title"]: item for item in report["watch"]}


# ------------------------------------------------------------------ the watch list


def test_the_watch_list_comes_from_existing_data_and_only_holds_acts(world) -> None:
    watched = _watched(world.check())
    assert set(watched) == {
        world.old["title"],
        world.new["title"],
        world.amending["title"],
        world.verify["title"],
    }
    assert "curated_supersession" in watched[world.old["title"]]["reasons"]
    assert watched[world.old["title"]]["superseded_by"] == "The Invented New Code, 2030"
    assert "curated_in_force" in watched[world.new["title"]]["reasons"]
    assert "amending_act" in watched[world.amending["title"]]["reasons"]
    assert "note_asks_to_verify_amendments" in watched[world.verify["title"]]["reasons"]


def test_the_repeal_table_alone_puts_an_act_on_the_list(world) -> None:
    # A title the repeal table knows, with nothing in the curated table about it.
    world.table.write_text(json.dumps({"entries": []}))
    currency._entries.cache_clear()
    world.rows = [_row("The Indian Penal Code, 1860")]
    world.write_manifest()
    assert "repeal_table" in world.check()["watch"][0]["reasons"]


# ------------------------------------------------------------------ the offline check


def test_a_first_check_records_and_reports_a_clean_baseline(world) -> None:
    report = world.check()
    assert report["mode"] == "offline"
    assert report["findings"] == []
    assert report["coverage"] == {"checked": 3, "no_local_source": 1}
    watched = _watched(report)
    assert watched[world.old["title"]]["last_checked"] == NOW.isoformat()
    # Never compared, so it must not claim a check.
    assert watched[world.amending["title"]]["last_checked"] is None
    assert watched[world.amending["title"]]["standing"] == "no_local_source"


def test_a_newer_source_date_is_a_finding(world) -> None:
    world.check()
    world.write_sources([_source(world.old, current_as_of="2026-11-01"), _source(world.new), _source(world.verify)])
    report = world.check()
    assert _kinds(report) == ["source_date_newer"]
    assert report["findings"][0]["recorded"] == "2026-10-03"
    assert report["findings"][0]["observed"] == "2026-11-01"


def test_a_different_checksum_for_the_same_source_is_a_finding(world) -> None:
    (world.candidates / world.new["original_filename"]).write_bytes(b"a different file")
    report = world.check()
    assert _kinds(report) == ["local_copy_differs"]
    assert report["findings"][0]["recorded"] == world.new["sha256"]


def test_a_matching_checksum_is_not_a_finding(world, tmp_path) -> None:
    content = b"exactly this file"
    world.new["sha256"] = hashlib.sha256(content).hexdigest()
    world.write_manifest()
    (world.candidates / world.new["original_filename"]).write_bytes(content)
    assert world.check()["findings"] == []


def test_a_title_match_alone_is_not_compared_by_checksum(world) -> None:
    """It may be another edition, so a different checksum there would mean nothing."""
    other_edition = {**_source(world.new), "url": "https://acts.example.gov.in/other.pdf", "filename": "other.pdf"}
    world.write_sources([other_edition])
    (world.candidates / "other.pdf").write_bytes(b"another edition")
    assert "local_copy_differs" not in _kinds(world.check())


def test_a_replaced_manifest_file_is_a_finding(world) -> None:
    world.check()
    world.new["sha256"] = "f" * 64
    world.write_manifest()
    assert _kinds(world.check()) == ["manifest_file_changed"]


def test_a_source_list_that_disagrees_with_the_table_is_a_finding(world) -> None:
    world.write_sources([_source(world.new, legal_status="REPEALED_SAVED")])
    report = world.check()
    assert _kinds(report) == ["source_list_says_repealed"]
    assert "REPEALED_SAVED" in report["findings"][0]["detail"]


def test_a_stale_curated_table_is_a_finding(world) -> None:
    table = json.loads(world.table.read_text())
    table["reviewed_on"] = "2026-01-01"
    world.table.write_text(json.dumps(table))
    assert _kinds(world.check()) == ["currency_table_review_overdue"]


def test_a_successor_the_corpus_does_not_hold_is_a_finding(world) -> None:
    world.rows = [world.old]
    world.write_manifest()
    report = world.check()
    assert _kinds(report) == ["successor_not_in_corpus"]
    assert report["findings"][0]["observed"] == "The Invented New Code, 2030"


def test_a_finding_keeps_its_identity_and_first_seen_across_runs(world) -> None:
    world.check()
    world.write_sources([_source(world.old, current_as_of="2026-11-01"), _source(world.new), _source(world.verify)])
    first = world.check()["findings"][0]
    # The stored date has now moved, so re-create the disagreement a run would keep.
    later = datetime(2026, 11, 9, tzinfo=timezone.utc)
    world.check(now=later)
    report_path = world.root / amendment_watch.REPORT_RELATIVE
    assert json.loads(report_path.read_text())["checked_at"] == later.isoformat()
    assert first["first_seen"] == NOW.isoformat()


def test_the_check_never_touches_the_manifest_or_the_table(world) -> None:
    manifest = (world.root / "metadata/canonical_documents.jsonl").read_text()
    table = world.table.read_text()
    world.check()
    assert (world.root / "metadata/canonical_documents.jsonl").read_text() == manifest
    assert world.table.read_text() == table


def test_output_can_go_somewhere_else_entirely(world, tmp_path) -> None:
    out = tmp_path / "elsewhere"
    world.check(output_root=out)
    assert (out / amendment_watch.REPORT_RELATIVE).is_file()
    assert not (world.root / amendment_watch.REPORT_RELATIVE).exists()


# ------------------------------------------------------------------- the network


def test_no_network_is_used_by_default(world, monkeypatch) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("the default run must not reach the network")

    monkeypatch.setattr("urllib.request.OpenerDirector.open", forbidden)
    monkeypatch.setattr("socket.create_connection", forbidden)
    report = world.check()
    assert report["fetch"] == {}


def _answers(mapping):
    calls: list[tuple[str, float]] = []

    def requester(url, *, allowed, timeout):
        calls.append((url, timeout))
        result = mapping(url)
        if isinstance(result, Exception):
            raise result
        return result

    requester.calls = calls
    return requester


def test_fetch_compares_headers_against_the_record_and_passes_a_timeout(world) -> None:
    state = {"etag": "one", "last_modified": None, "content_length": "10"}
    requester = _answers(lambda _url: dict(state))
    first = world.check(fetch=True, requester=requester, timeout=7.0)
    assert "remote_headers_changed" not in _kinds(first), "the first answer is the baseline"
    assert first["fetch"]["answered"] >= 1
    assert {timeout for _, timeout in requester.calls} == {7.0}

    state["etag"] = "two"
    assert "remote_headers_changed" in _kinds(world.check(fetch=True, requester=requester))


def test_a_host_that_refuses_is_left_alone(world) -> None:
    requester = _answers(lambda _url: urllib.error.HTTPError(_url, 403, "Forbidden", {}, None))
    report = world.check(fetch=True, requester=requester)
    assert len(requester.calls) == 1, "no retry, and no further requests to that host"
    assert report["fetch"]["refused_or_unreachable"] == 1
    assert report["fetch"]["host_refused_earlier"] == 3
    assert report["mode"] == "network"


def test_the_fetch_limit_is_respected(world) -> None:
    requester = _answers(lambda _url: {"etag": "x"})
    report = world.check(fetch=True, fetch_limit=2, requester=requester)
    assert len(requester.calls) == 2
    assert report["fetch"]["not_reached_limit"] == 2


def test_only_official_hosts_from_the_source_lists_are_allowed() -> None:
    sources = [
        amendment_watch.LocalSource("a", "https://indiacode.gov.in/a.pdf", "", None, None, None, "x"),
        amendment_watch.LocalSource("b", "https://ncdrc.nic.in/b.pdf", "", None, None, None, "x"),
        amendment_watch.LocalSource("c", "https://mirror.example.com/c.pdf", "", None, None, None, "x"),
    ]
    assert amendment_watch.official_hosts(sources) == {"indiacode.gov.in", "ncdrc.nic.in"}


def test_a_host_outside_the_list_is_never_requested(world) -> None:
    world.new["source_url"] = "https://mirror.example.com/copy.pdf"
    world.write_manifest()
    requester = _answers(lambda _url: {"etag": "x"})
    world.write_sources([_source(world.old), _source(world.verify)])
    report = world.check(fetch=True, requester=requester)
    assert all("mirror.example.com" not in url for url, _ in requester.calls)
    assert report["fetch"]["host_not_allowed"] >= 1


@pytest.mark.parametrize(
    "url",
    ["https://mirror.example.com/a.pdf", "http://indiacode.gov.in/a.pdf"],
)
def test_the_real_requester_refuses_before_any_connection(url) -> None:
    with pytest.raises(ValueError):
        amendment_watch.head_request(url, allowed={"indiacode.gov.in"}, timeout=1)


def test_a_redirect_off_the_official_hosts_is_refused() -> None:
    handler = amendment_watch._StayOnOfficialHosts({"indiacode.gov.in"})
    with pytest.raises(urllib.error.URLError):
        handler.redirect_request(None, None, 302, "Found", {}, "https://mirror.example.com/a.pdf")


# ---------------------------------------------------------------------- the script


def _load_script():
    path = Path(__file__).resolve().parents[2] / "scripts/check_amendments.py"
    spec = importlib.util.spec_from_file_location("check_amendments_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_script_reports_clearly_with_no_network(world, capsys) -> None:
    code = _load_script().main(
        ["--kb-root", str(world.root), "--sources-dir", str(world.sources), "--candidates-dir", str(world.candidates)]
    )
    output = capsys.readouterr().out
    assert code == 0
    assert "(offline)" in output
    assert "network: not used" in output
    assert "Watched Acts: 4" in output
    assert (world.root / amendment_watch.REPORT_RELATIVE).is_file()


def test_the_script_says_so_when_there_is_no_manifest(tmp_path, capsys) -> None:
    code = _load_script().main(["--kb-root", str(tmp_path)])
    assert code == 2
    assert "No manifest" in capsys.readouterr().err


# ---------------------------------------------------------------------- the console


@pytest_asyncio.fixture(loop_scope="session")
async def admin_client():
    admin = await provision_test_user(
        name="Watch Admin", email=unique_email("watch-admin"), password=PASSWORD, role="admin"
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {admin['access_token']}"
        yield client


@pytest.mark.integration
async def test_the_console_says_when_no_check_has_run(world, monkeypatch, admin_client) -> None:
    monkeypatch.setattr(settings, "legal_kb_root", str(world.root))
    response = await admin_client.get("/admin/console/corpus/amendments")
    assert response.status_code == 200
    assert response.json()["has_run"] is False


@pytest.mark.integration
async def test_the_console_shows_findings_and_records_a_review(world, monkeypatch, admin_client) -> None:
    monkeypatch.setattr(settings, "legal_kb_root", str(world.root))
    (world.candidates / world.new["original_filename"]).write_bytes(f"{uuid.uuid4()}".encode())
    report = world.check()
    finding_id = report["findings"][0]["id"]

    view = (await admin_client.get("/admin/console/corpus/amendments", params={"page_size": 2})).json()
    assert view["has_run"] is True and view["open_findings"] == 1
    assert view["findings"][0]["review_status"] == "open"
    assert len(view["watch"]) == 2 and view["watch_total"] == 4

    saved = await admin_client.put(
        f"/admin/console/corpus/amendments/findings/{finding_id}",
        json={"status": "reviewed", "note": "Not a new edition."},
    )
    assert saved.status_code == 200

    world.check()
    view = (await admin_client.get("/admin/console/corpus/amendments")).json()
    assert view["open_findings"] == 0, "the same finding stays answered on the next run"
    assert view["findings"][0]["review_note"] == "Not a new edition."


@pytest.mark.integration
async def test_a_finding_not_in_the_latest_check_cannot_be_reviewed(world, monkeypatch, admin_client) -> None:
    monkeypatch.setattr(settings, "legal_kb_root", str(world.root))
    world.check()
    response = await admin_client.put(
        "/admin/console/corpus/amendments/findings/nonexistent", json={"status": "reviewed"}
    )
    assert response.status_code == 404


@pytest.mark.integration
async def test_a_citizen_cannot_read_the_findings(world, monkeypatch) -> None:
    citizen = await provision_test_user(
        name="Not Admin", email=unique_email("watch-citizen"), password=PASSWORD, role="citizen"
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/admin/console/corpus/amendments", headers={"Authorization": f"Bearer {citizen['access_token']}"}
        )
    assert response.status_code == 403
