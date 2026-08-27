#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright 2026 voltchange contributors
# SPDX-License-Identifier: Apache-2.0

"""Compute the exact source digest bound into the container image label."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXED_PATHS = (
    ROOT / ".dockerignore",
    ROOT / "Dockerfile",
    ROOT / "LICENSE",
    ROOT / "THIRD_PARTY_NOTICES.md",
    ROOT / "runtime",
    ROOT / "ossp_router",
)


def _files(path: Path):
    if path.is_file():
        yield path
        return
    for candidate in sorted(path.rglob("*")):
        if candidate.is_file() and "__pycache__" not in candidate.parts:
            yield candidate


def _selected_directory(value: str, label: str) -> Path:
    selected = (ROOT / value).resolve()
    if not selected.is_relative_to(ROOT) or not selected.is_dir():
        raise ValueError(f"{label} must be a directory inside this repository")
    return selected


def build_manifest(implementation: str, tokenizer: str) -> dict[str, object]:
    implementation_root = _selected_directory(implementation, "implementation")
    tokenizer_root = _selected_directory(tokenizer, "tokenizer")
    paths = (*FIXED_PATHS, implementation_root, tokenizer_root)
    files = []
    seen = set()
    for source in paths:
        for path in _files(source):
            relative = path.relative_to(ROOT).as_posix()
            if relative in seen:
                continue
            seen.add(relative)
            payload = path.read_bytes()
            files.append(
                {
                    "path": relative,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size": len(payload),
                }
            )
    files.sort(key=lambda item: item["path"])
    return {
        "schema_version": 2,
        "implementation": implementation,
        "tokenizer": tokenizer,
        "files": files,
    }


def canonical_bytes(manifest: dict[str, object]) -> bytes:
    return json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--implementation", default="router_impl")
    parser.add_argument("--tokenizer", default="tokenizer_impl")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    manifest = build_manifest(args.implementation, args.tokenizer)
    if args.as_json:
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(hashlib.sha256(canonical_bytes(manifest)).hexdigest())


if __name__ == "__main__":
    main()
