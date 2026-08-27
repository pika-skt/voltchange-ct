# SPDX-FileCopyrightText: Copyright 2026 voltchange contributors
# SPDX-License-Identifier: Apache-2.0

"""Minimal alternate tokenizer used to demonstrate the swap contract."""

from __future__ import annotations

TOKENIZER_ID = "whitespace-casefold-number-v1"


def tokenize(text: str) -> tuple[str, ...]:
    """Split on whitespace, case-fold, and normalize decimal tokens."""

    return tuple(
        "<number>" if token.isdecimal() else token.casefold() for token in text.split()
    )
