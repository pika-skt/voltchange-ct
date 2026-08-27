# SPDX-FileCopyrightText: Copyright 2026 voltchange contributors
# SPDX-License-Identifier: Apache-2.0

"""Official one-tier container entry point."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from ossp_router.heuristic import write_submission_atomic
from ossp_router.protocol import (
    TIERS,
    ProtocolError,
    load_bundled_policy,
    load_input,
    load_policy,
)
from runtime.adapter import RouterContractError, make_submission


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="router-run",
        description="Run one content-only router tier.",
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--tier", choices=TIERS, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--policy", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        inputs = load_input(args.input)
        policy = (
            load_policy(args.policy)
            if args.policy is not None
            else load_bundled_policy()
        )
        submission = make_submission(inputs, policy, args.tier)
        write_submission_atomic(args.output, submission)
    except (
        ImportError,
        OSError,
        ProtocolError,
        RouterContractError,
        ValueError,
    ) as exc:
        print(f"router error: {exc}", file=sys.stderr)
        return 2
    print(f"OK: wrote {args.tier} submission")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
