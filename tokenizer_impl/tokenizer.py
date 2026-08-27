# SPDX-FileCopyrightText: Copyright 2026 SK TELECOM CO., LTD.
# SPDX-License-Identifier: Apache-2.0

"""Dependency-free tokenization used to train the public hash/regex artifact."""

from __future__ import annotations

import re

TOKENIZER_ID = "regex-casefold-number-v1"

_TOKEN = re.compile(r"[A-Za-z]+|[가-힣]+|\d+|[^\w\s]", re.UNICODE)


def tokenize(text: str) -> tuple[str, ...]:
    """Split text, case-fold words, and normalize standalone decimal tokens."""

    result = []
    for token in _TOKEN.findall(text):
        normalized = token.casefold()
        if normalized.isdecimal():
            normalized = "<number>"
        result.append(normalized)
    return tuple(result)
