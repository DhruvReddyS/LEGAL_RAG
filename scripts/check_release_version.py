#!/usr/bin/env python3
"""Fail when the desktop release versions or requested Git tag disagree."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path


SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check package.json, package-lock.json, Tauri and Cargo versions."
    )
    parser.add_argument(
        "--tag",
        help="Optional release tag. It must be exactly v<desktop version>.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root (defaults to the parent of scripts/).",
    )
    return parser.parse_args()


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def main() -> int:
    args = _arguments()
    root = args.root.resolve()
    frontend = root / "frontend"

    package = _load_json(frontend / "package.json")
    package_lock = _load_json(frontend / "package-lock.json")
    tauri_config = _load_json(frontend / "src-tauri" / "tauri.conf.json")
    cargo_manifest = _load_toml(frontend / "src-tauri" / "Cargo.toml")
    cargo_lock = _load_toml(frontend / "src-tauri" / "Cargo.lock")

    desktop_package = next(
        (
            item
            for item in cargo_lock.get("package", [])
            if item.get("name") == cargo_manifest["package"]["name"]
        ),
        None,
    )
    versions = {
        "frontend/package.json": package.get("version"),
        "frontend/package-lock.json": package_lock.get("version"),
        'frontend/package-lock.json packages[""].version': package_lock.get(
            "packages", {}
        ).get("", {}).get("version"),
        "frontend/src-tauri/tauri.conf.json": tauri_config.get("version"),
        "frontend/src-tauri/Cargo.toml": cargo_manifest.get("package", {}).get(
            "version"
        ),
        "frontend/src-tauri/Cargo.lock": (
            desktop_package.get("version") if desktop_package else None
        ),
    }

    missing = [name for name, version in versions.items() if not isinstance(version, str)]
    if missing:
        print("Release version check failed: missing version in:", file=sys.stderr)
        for name in missing:
            print(f"  - {name}", file=sys.stderr)
        return 1

    expected = versions["frontend/package.json"]
    if not SEMVER_RE.fullmatch(expected):
        print(
            f"Release version check failed: {expected!r} is not valid SemVer.",
            file=sys.stderr,
        )
        return 1

    mismatches = {
        name: version for name, version in versions.items() if version != expected
    }
    if mismatches:
        print(
            f"Release version check failed: expected every version to be {expected}.",
            file=sys.stderr,
        )
        for name, version in mismatches.items():
            print(f"  - {name}: {version!r}", file=sys.stderr)
        return 1

    if args.tag is not None:
        expected_tag = f"v{expected}"
        if args.tag != expected_tag:
            print(
                "Release version check failed: "
                f"tag {args.tag!r} must be {expected_tag!r}.",
                file=sys.stderr,
            )
            return 1

    suffix = f" and tag {args.tag}" if args.tag else ""
    print(f"Desktop release version is consistent: {expected}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
