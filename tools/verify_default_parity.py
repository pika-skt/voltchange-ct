#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright 2026 voltchange contributors
# SPDX-License-Identifier: Apache-2.0

"""Verify the blended router preserves official score/cost head predictions."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType

from ossp_router.protocol import load_input
from router_impl.hash_regex import load_artifact, predict_episode

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OFFICIAL_REPO = ROOT.parent / "ossp-2026-llm-router-challenge"
_TOKEN = re.compile(r"[A-Za-z]+|[가-힣]+|\d+|[^\w\s]", re.UNICODE)


def _tokenize(text: str) -> tuple[str, ...]:
    result = []
    for token in _TOKEN.findall(text):
        normalized = token.casefold()
        if normalized.isdecimal():
            normalized = "<number>"
        result.append(normalized)
    return tuple(result)


def _load_official_baseline(repository: Path) -> ModuleType:
    source = repository.resolve() / "baselines" / "hash_regex.py"
    spec = importlib.util.spec_from_file_location("_frozen_official_hash_regex", source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load official baseline from {source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--official-repo",
        type=Path,
        default=DEFAULT_OFFICIAL_REPO,
    )
    args = parser.parse_args()

    inputs = load_input(args.input)
    official = _load_official_baseline(args.official_repo)
    official_artifact = official.load_artifact(
        args.official_repo.resolve() / "baselines" / "hash-regex-public.v1.json"
    )
    runtime_artifact = load_artifact(
        ROOT / "router_impl" / "hash-regex-public.v1.json"
    )
    mismatches = 0
    for episode in inputs.episodes:
        expected = official.predict_episode(episode, official_artifact)
        actual = predict_episode(episode, runtime_artifact, tokenize=_tokenize)
        mismatches += expected != actual
    print(
        json.dumps(
            {
                "official_head_parity": {
                    "episodes": len(inputs.episodes),
                    "prediction_mismatches": mismatches,
                }
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
