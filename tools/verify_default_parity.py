#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright 2026 voltchange contributors
# SPDX-License-Identifier: Apache-2.0

"""Compare the adapted default router with the direct official baseline path."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

from ossp_router.protocol import TIERS, load_bundled_policy, load_input
from runtime.adapter import make_submission

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OFFICIAL_REPO = ROOT.parent / "ossp-2026-llm-router-challenge"


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
    policy = load_bundled_policy()
    official = _load_official_baseline(args.official_repo)
    artifact = official.load_artifact(
        args.official_repo.resolve() / "baselines" / "hash-regex-public.v1.json"
    )
    rows = []
    failed = False
    for tier in TIERS:
        direct = official.make_hash_regex_submission(
            inputs, policy, artifact, tier
        ).submission
        adapted = make_submission(inputs, policy, tier)
        direct_choices = tuple(item.model_id for item in direct.decisions)
        adapted_choices = tuple(item.model_id for item in adapted.decisions)
        mismatches = sum(
            left != right
            for left, right in zip(direct_choices, adapted_choices, strict=True)
        )
        failed = failed or mismatches != 0
        rows.append(
            {"tier": tier, "episodes": len(direct_choices), "mismatches": mismatches}
        )
    print(json.dumps({"parity": rows}, indent=2, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
