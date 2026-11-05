#!/usr/bin/env python3
"""Add, replace or retire one corpus document without a rebuild.

--collection is required on every command. There is no default on purpose. Every
command prints its plan first, and --dry-run stops there.

    corpus_lifecycle.py add     --collection C --document-id ID [--from-manifest F]
    corpus_lifecycle.py add     --collection C --pending
    corpus_lifecycle.py replace --collection C --old OLD --new NEW [--from-manifest F]
    corpus_lifecycle.py retire  --collection C --document-id ID

The logic is in backend/app/ingestion/lifecycle.py.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.core.qdrant import create_qdrant_client  # noqa: E402
from app.ingestion import lifecycle  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    def command(name: str, help_text: str) -> argparse.ArgumentParser:
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("--collection", required=True, help="The Qdrant collection to change.")
        sub.add_argument("--dry-run", action="store_true", help="Print the plan and change nothing.")
        sub.add_argument("--kb-root", type=Path, help="Corpus root. Defaults to LEGAL_KB_ROOT.")
        return sub

    add = command("add", "Index a document and confirm it is in.")
    target = add.add_mutually_exclusive_group(required=True)
    target.add_argument("--document-id", help="A document_id or canonical_document_id.")
    target.add_argument(
        "--pending", action="store_true", help="Every manifest document this collection has not completed."
    )
    add.add_argument("--from-manifest", type=Path, help="Take the row from this file if the manifest lacks it.")

    replace = command("replace", "Add a new document, then retire the old one once it is confirmed.")
    replace.add_argument("--old", required=True, help="canonical_document_id of the copy to retire.")
    replace.add_argument("--new", required=True, help="document_id or canonical_document_id of the new copy.")
    replace.add_argument("--from-manifest", type=Path, help="Take the new row from this file if the manifest lacks it.")
    replace.add_argument("--yes", action="store_true", help="Do not ask before retiring.")

    retire = command("retire", "Remove a document's points, manifest rows and ledger entry.")
    retire.add_argument("--document-id", required=True, help="canonical_document_id of the document.")
    retire.add_argument("--yes", action="store_true", help="Do not ask before retiring.")
    return parser.parse_args(argv)


def _print(lines: list[str]) -> None:
    print("\n".join(lines), flush=True)


def _confirmed(args: argparse.Namespace) -> bool:
    """A destructive command must be asked for, or typed for, not merely not stopped."""
    if args.yes:
        return True
    if not sys.stdin.isatty():
        print("Not retiring: pass --yes when there is no terminal to ask at.", file=sys.stderr)
        return False
    answer = input(f"Type the collection name to go ahead ({args.collection}): ")
    return answer.strip() == args.collection


def _report_blockers(root: Path, collection: str) -> None:
    for reason in lifecycle.ingestion_blockers(root, collection):
        print(f"  would refuse, ingestion is running: {reason}")


async def run(args: argparse.Namespace) -> int:
    root = (args.kb_root or Path(settings.legal_kb_root)).resolve()
    client = create_qdrant_client()
    try:
        if args.command == "retire":
            plan = await lifecycle.plan_retire(root, args.collection, args.document_id, client)
            _print(plan.describe())
            if plan.nothing_to_do:
                print("That id matches nothing. Check it.", file=sys.stderr)
                return 1
            if args.dry_run:
                _report_blockers(root, args.collection)
                print("dry run: nothing changed")
                return 0
            if not _confirmed(args):
                return 1
            result = await lifecycle.execute_retire(root, args.collection, args.document_id, client)
            print(f"retired: {result['points_removed']} point(s) removed")
            return 0

        if args.command == "replace":
            add_plan, retire_plan = await lifecycle.plan_replace(
                root, args.collection, args.old, args.new, client, from_manifest=args.from_manifest
            )
            _print(add_plan.describe())
            print("then, only once that is confirmed:")
            _print(retire_plan.describe())
            if args.dry_run:
                _report_blockers(root, args.collection)
                print("dry run: nothing changed")
                return 0
            if not _confirmed(args):
                return 1
            result = await lifecycle.execute_replace(
                root, args.collection, args.old, args.new, client, from_manifest=args.from_manifest
            )
            print(json.dumps({"points_added": result["added"]["points"], "points_retired": result["retired"]["points_removed"]}))
            return 0

        wanted = (
            [item.canonical_document_id for item in lifecycle.pending_documents(root, args.collection)]
            if args.pending
            else [args.document_id]
        )
        if args.pending:
            print(f"{len(wanted)} document(s) pending in {args.collection}")
        failures = 0
        for item in wanted:
            try:
                plan = await lifecycle.plan_add(root, args.collection, item, client, from_manifest=args.from_manifest)
                _print(plan.describe())
                if args.dry_run:
                    continue
                result = await lifecycle.execute_add(
                    root, args.collection, item, client, from_manifest=args.from_manifest
                )
                print(f"confirmed: {result['points']} point(s)")
            except lifecycle.LifecycleRefused as exc:
                failures += 1
                print(f"refused: {item}: {exc}", file=sys.stderr)
        if args.dry_run:
            _report_blockers(root, args.collection)
            print("dry run: nothing changed")
        return 1 if failures else 0
    except lifecycle.LifecycleRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    finally:
        await client.close()


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
