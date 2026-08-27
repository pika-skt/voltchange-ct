#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright 2026 voltchange contributors
# SPDX-License-Identifier: Apache-2.0

"""Run all tiers locally and report time, RSS, output size, and decision digests."""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import time
from pathlib import Path

from ossp_router.protocol import (
    TIERS,
    dumps_json,
    load_bundled_policy,
    load_input,
    submission_to_dict,
)
from runtime.adapter import make_submission


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--max-seconds", type=float, default=90.0)
    args = parser.parse_args()

    inputs = load_input(args.input)
    policy = load_bundled_policy()
    rows = []
    failed = False
    for tier in TIERS:
        started = time.perf_counter()
        submission = make_submission(inputs, policy, tier)
        elapsed = time.perf_counter() - started
        encoded = dumps_json(submission_to_dict(submission)).encode("utf-8")
        failed = failed or elapsed > args.max_seconds or len(encoded) > 4 * 1024 * 1024
        rows.append(
            {
                "tier": tier,
                "elapsed_seconds": elapsed,
                "output_bytes": len(encoded),
                "decision_sha256": hashlib.sha256(encoded).hexdigest(),
            }
        )
    usage = resource.getrusage(resource.RUSAGE_SELF)
    print(
        json.dumps(
            {
                "episodes": len(inputs.episodes),
                "max_rss_kib_linux_or_bytes_macos": usage.ru_maxrss,
                "tiers": rows,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
