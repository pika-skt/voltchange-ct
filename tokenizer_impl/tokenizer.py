# SPDX-FileCopyrightText: Copyright 2026 voltchange contributors
# SPDX-License-Identifier: Apache-2.0

"""MeCab-ko tokenization paired with the frozen hybrid gain artifact."""

from __future__ import annotations

import unicodedata
from functools import lru_cache

import mecab_ko

TOKENIZER_ID = "mecab-ko-hybrid-pos-v1"

_CONNECTORS = "'\N{RIGHT SINGLE QUOTATION MARK}_-\N{HYPHEN}\N{NON-BREAKING HYPHEN}\N{EN DASH}\N{EM DASH}"


def _is_latin_letter(character: str) -> bool:
    if "A" <= character <= "Z" or "a" <= character <= "z":
        return True
    if not character.isalpha():
        return False
    return "LATIN" in unicodedata.name(character, "")


def _latin_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    position = 0
    while position < len(text):
        if not (_is_latin_letter(text[position]) or text[position].isdecimal()):
            position += 1
            continue
        start = position
        has_latin = _is_latin_letter(text[position])
        position += 1
        while position < len(text):
            character = text[position]
            if _is_latin_letter(character) or character.isdecimal():
                has_latin = has_latin or _is_latin_letter(character)
                position += 1
                continue
            if unicodedata.combining(character):
                position += 1
                continue
            if (
                character in _CONNECTORS
                and position + 1 < len(text)
                and (
                    _is_latin_letter(text[position + 1])
                    or text[position + 1].isdecimal()
                )
            ):
                position += 1
                continue
            break
        if has_latin:
            spans.append((start, position))
    return spans


@lru_cache(maxsize=1)
def _tagger() -> mecab_ko.Tagger:
    return mecab_ko.Tagger()


def _parse_unprotected(text: str) -> list[str]:
    if not text.strip():
        return []
    tokens: list[str] = []
    for line in _tagger().parse(text).splitlines():
        if line == "EOS":
            break
        form, separator, features = line.partition("\t")
        if separator:
            tag = features.split(",", 1)[0]
            tokens.append(f"{tag}\t{form}")
    return tokens


def tokenize(text: str) -> tuple[str, ...]:
    """Return reversible ``POS<TAB>form`` tokens with protected Latin spans."""

    tokens: list[str] = []
    cursor = 0
    for start, end in _latin_spans(text):
        tokens.extend(_parse_unprotected(text[cursor:start]))
        tokens.append(f"SL\t{text[start:end]}")
        cursor = end
    tokens.extend(_parse_unprotected(text[cursor:]))
    return tuple(tokens)
