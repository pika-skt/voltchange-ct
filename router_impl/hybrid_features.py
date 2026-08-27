# SPDX-FileCopyrightText: Copyright 2026 voltchange contributors
# SPDX-License-Identifier: Apache-2.0

"""Runtime copy of the frozen MeCab hybrid lexical and structural features."""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Sequence

from runtime.contract import ContentEpisode

STRUCTURAL_FEATURE_NAMES = (
    "log_character_count",
    "log_word_count",
    "log_sentence_count",
    "log_message_count",
    "hangul_ratio",
    "log_code_marker_count",
    "log_math_marker_count",
    "numeric_density",
    "long_context",
    "log_reasoning_marker_count",
    "formal_reasoning",
    "program_analysis",
    "log_multi_constraint_count",
    "simple_transform",
)

MAX_ENGLISH_PARTS = 16
MAX_FEATURE_VALUE_CHARS = 96

_CONNECTORS = "'\N{RIGHT SINGLE QUOTATION MARK}_-\N{HYPHEN}\N{NON-BREAKING HYPHEN}\N{EN DASH}\N{EM DASH}"
_CONNECTOR_RE = re.compile(f"[{re.escape(_CONNECTORS)}]+")
_CAMEL_OR_NUMBER_RE = re.compile(
    r"[A-Z]+(?=[A-Z][a-z]|[0-9]|$)|[A-Z]?[a-z]+|[A-Z]+|[0-9]+"
)
_DIGIT_RUN_RE = re.compile(r"\d+")
_CODE_MARKERS = re.compile(
    r"```|(?:^|\s)(?:def|class|function|SELECT|FROM|import|#include)\b|"
    r"[{};]\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_MATH_MARKERS = re.compile(r"[=+\-*/^∑∫√≈≠≤≥<>]|\\(?:frac|sum|int|sqrt)\b")
_NUMBER = re.compile(r"\d")
_WORD = re.compile(r"[A-Za-z가-힣]+")
_SENTENCE_END = re.compile(r"[.!?。！？]")
_REASONING_WORDS = re.compile(
    r"\b(?:prove|derive|reason|analyze|explain why|algorithm|complexity|"
    r"증명|유도|추론|분석|알고리즘|복잡도)\b",
    re.IGNORECASE,
)
_FORMAL_REASONING = re.compile(
    r"\b(?:prove|derive|theorem|lemma|counterexample|induction|"
    r"증명|유도|정리|보조정리|반례|귀납)\b",
    re.IGNORECASE,
)
_PROGRAM_ANALYSIS = re.compile(
    r"```|\b(?:traceback|exception|complexity|big[- ]?o|"
    r"시간\s*복잡도|공간\s*복잡도|예외|스택\s*추적)\b",
    re.IGNORECASE,
)
_MULTI_CONSTRAINT = re.compile(
    r"\b(?:exactly|at least|at most|must|only|without|"
    r"정확히|이상|이하|반드시|오직|제외하고)\b",
    re.IGNORECASE,
)
_SIMPLE_TRANSFORM = re.compile(
    r"\b(?:summari[sz]e|rewrite|translate|list|extract|"
    r"요약|바꾸|번역|나열|추출)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Token:
    form: str
    tag: str


@dataclass(frozen=True)
class EnglishAliases:
    whole: str
    digit_normalized: str
    parts: tuple[str, ...]
    camel_parts: tuple[str, ...]
    contraction_parts: tuple[str, ...]


def episode_text(episode: ContentEpisode) -> str:
    return "\n".join(message.content for message in episode.messages)


def decode_tokens(values: Sequence[str]) -> tuple[Token, ...]:
    tokens = []
    for value in values:
        tag, separator, form = value.partition("\t")
        if not separator or not tag or not form:
            raise ValueError("MeCab token must use non-empty POS<TAB>form encoding")
        tokens.append(Token(form=form, tag=tag))
    return tuple(tokens)


def _is_latin_letter(character: str) -> bool:
    if "A" <= character <= "Z" or "a" <= character <= "z":
        return True
    if not character.isalpha():
        return False
    return "LATIN" in unicodedata.name(character, "")


def _canonical_text(value: str) -> str:
    return (
        unicodedata.normalize("NFKC", value)
        .replace("\N{RIGHT SINGLE QUOTATION MARK}", "'")
        .replace("\N{HYPHEN}", "-")
        .replace("\N{NON-BREAKING HYPHEN}", "-")
        .replace("\N{EN DASH}", "-")
        .replace("\N{EM DASH}", "-")
    )


def _bounded_value(value: str) -> str:
    if len(value) <= MAX_FEATURE_VALUE_CHARS:
        return value
    digest = hashlib.blake2b(value.encode("utf-8"), digest_size=8).hexdigest()
    prefix_length = MAX_FEATURE_VALUE_CHARS - len(digest) - 1
    return f"{value[:prefix_length]}~{digest}"


def _bounded_parts(parts: Sequence[str], maximum: int) -> tuple[str, ...]:
    if len(parts) <= maximum:
        return tuple(parts)
    head = maximum // 2
    tail = maximum - head - 1
    tail_parts = parts[-tail:] if tail else ()
    return (*parts[:head], "<parts-truncated>", *tail_parts)


def _camel_and_number_parts(value: str) -> tuple[str, ...]:
    parts = _CAMEL_OR_NUMBER_RE.findall(value)
    if not parts or "".join(parts) != value:
        return (value.casefold(),) if value else ()
    return tuple(
        "<number>" if part.isdecimal() else part.casefold() for part in parts
    )


def _contraction_parts(value: str) -> tuple[str, ...]:
    current = value.casefold()
    expansions: list[str] = []
    suffixes = (
        ("'re", "are"),
        ("'ve", "have"),
        ("'ll", "will"),
        ("'m", "am"),
        ("'d", "would_or_had"),
        ("'s", "is_has_or_possessive"),
    )
    while True:
        if current.endswith("n't") and len(current) > 3:
            stem = current[:-3]
            current = {"ca": "can", "wo": "will", "sha": "shall", "ai": "be"}.get(
                stem, stem
            )
            expansions.append("not")
            continue
        matched = False
        for suffix, expansion in suffixes:
            if current.endswith(suffix) and len(current) > len(suffix):
                expansions.append(expansion)
                current = current[: -len(suffix)]
                matched = True
                break
        if not matched:
            break
    if not expansions:
        return ()
    return (current, *reversed(expansions))


def english_aliases(form: str) -> EnglishAliases:
    canonical = _canonical_text(form)
    normalized = canonical.casefold()
    whole = _bounded_value(normalized)
    digit_normalized = _bounded_value(_DIGIT_RUN_RE.sub("<number>", normalized))
    contraction_parts = _contraction_parts(canonical)
    atomic_parts: list[str] = []
    camel_parts: list[str] = []
    for segment in _CONNECTOR_RE.split(canonical):
        if not segment:
            continue
        split = _camel_and_number_parts(segment)
        atomic_parts.extend(split)
        if len(split) > 1 or (segment != segment.casefold() and len(split) > 1):
            camel_parts.extend(split)
    if contraction_parts:
        atomic_parts = list(contraction_parts)
    return EnglishAliases(
        whole=whole,
        digit_normalized=digit_normalized,
        parts=_bounded_parts(
            tuple(_bounded_value(part) for part in atomic_parts), MAX_ENGLISH_PARTS
        ),
        camel_parts=_bounded_parts(
            tuple(_bounded_value(part) for part in camel_parts), MAX_ENGLISH_PARTS
        ),
        contraction_parts=_bounded_parts(
            tuple(_bounded_value(part) for part in contraction_parts),
            MAX_ENGLISH_PARTS,
        ),
    )


def _normalized_token_form(token: Token) -> str:
    canonical = _canonical_text(token.form)
    if token.tag == "SN" or canonical.isdecimal():
        return "<number>"
    return _bounded_value(canonical.casefold())


def _stable_unique(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def hybrid_token_features(encoded_tokens: Sequence[str]) -> tuple[str, ...]:
    tokens = decode_tokens(encoded_tokens)
    normalized_forms: list[str] = []
    tags: list[str] = []
    form_tags: list[str] = []
    features: list[str] = []
    for token in tokens:
        form = _normalized_token_form(token)
        tag = _bounded_value(token.tag)
        form_tag = f"{form}/{tag}"
        normalized_forms.append(form)
        tags.append(tag)
        form_tags.append(form_tag)
        features.extend((f"tok:{form}", f"pos:{tag}", f"fp:{form_tag}"))
        if token.tag == "SL" and any(
            _is_latin_letter(character) for character in token.form
        ):
            aliases = english_aliases(token.form)
            features.append(f"en:{aliases.whole}")
            if aliases.digit_normalized != aliases.whole:
                features.append(f"en_norm:{aliases.digit_normalized}")
            features.extend(f"en_part:{part}" for part in _stable_unique(aliases.parts))
            features.extend(
                f"en_camel:{part}" for part in _stable_unique(aliases.camel_parts)
            )
            features.extend(
                f"en_contract:{part}"
                for part in _stable_unique(aliases.contraction_parts)
            )
            features.extend(
                f"en_part2:{left}\x1f{right}"
                for left, right in zip(aliases.parts, aliases.parts[1:])
            )
    features.extend(
        f"tok2:{left}\x1f{right}"
        for left, right in zip(normalized_forms, normalized_forms[1:])
    )
    features.extend(
        f"pos2:{left}\x1f{right}" for left, right in zip(tags, tags[1:])
    )
    features.extend(
        f"fp2:{left}\x1f{right}" for left, right in zip(form_tags, form_tags[1:])
    )
    return tuple(features)


def structural_features(episode: ContentEpisode) -> tuple[float, ...]:
    text = episode_text(episode)
    characters = len(text)
    nonspace = sum(not character.isspace() for character in text)
    hangul = sum("\uac00" <= character <= "\ud7a3" for character in text)
    word_count = len(_WORD.findall(text))
    sentence_count = max(1, len(_SENTENCE_END.findall(text)))
    code_marker_count = len(_CODE_MARKERS.findall(text))
    math_marker_count = len(_MATH_MARKERS.findall(text))
    number_count = len(_NUMBER.findall(text))
    reasoning_marker_count = len(_REASONING_WORDS.findall(text))
    return (
        math.log1p(characters),
        math.log1p(word_count),
        math.log1p(sentence_count),
        math.log1p(len(episode.messages)),
        hangul / max(1, nonspace),
        math.log1p(code_marker_count),
        math.log1p(math_marker_count),
        number_count / max(1, nonspace),
        float(characters >= 8_000),
        math.log1p(reasoning_marker_count),
        float(bool(_FORMAL_REASONING.search(text))),
        float(bool(_PROGRAM_ANALYSIS.search(text))),
        math.log1p(len(_MULTI_CONSTRAINT.findall(text))),
        float(bool(_SIMPLE_TRANSFORM.search(text))),
    )
