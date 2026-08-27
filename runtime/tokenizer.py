# SPDX-FileCopyrightText: Copyright 2026 voltchange contributors
# SPDX-License-Identifier: Apache-2.0

"""Load and validate the build-selected tokenizer implementation."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from importlib import import_module
from pathlib import Path
from types import ModuleType

_TOKENIZER_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")


class TokenizerContractError(ValueError):
    """Raised when a tokenizer is malformed or incompatible with a model."""


@dataclass(frozen=True)
class LoadedTokenizer:
    """Validated tokenizer metadata and its normalized callable."""

    tokenizer_id: str
    tokenize: Callable[[str], Sequence[str]]

    def __call__(self, text: str) -> tuple[str, ...]:
        if not isinstance(text, str):
            raise TokenizerContractError("tokenize() input must be a string")
        result = self.tokenize(text)
        if isinstance(result, (str, bytes)):
            raise TokenizerContractError(
                "tokenize() must return a sequence of token strings"
            )
        try:
            tokens = tuple(result)
        except TypeError as exc:
            raise TokenizerContractError(
                "tokenize() must return an iterable of token strings"
            ) from exc
        if any(not isinstance(token, str) or not token for token in tokens):
            raise TokenizerContractError(
                "tokenize() returned a non-string or empty token"
            )
        return tokens


def _load_from_module(module: ModuleType) -> LoadedTokenizer:
    tokenizer_id = getattr(module, "TOKENIZER_ID", None)
    if (
        not isinstance(tokenizer_id, str)
        or _TOKENIZER_ID.fullmatch(tokenizer_id) is None
    ):
        raise TokenizerContractError(
            "tokenizer_impl.tokenizer must export a valid TOKENIZER_ID"
        )
    tokenize = getattr(module, "tokenize", None)
    if not callable(tokenize):
        raise TokenizerContractError(
            "tokenizer_impl.tokenizer must export callable tokenize(text)"
        )

    module_file = getattr(module, "__file__", None)
    if not isinstance(module_file, str):
        raise TokenizerContractError("tokenizer module has no filesystem location")
    manifest_path = Path(module_file).resolve().with_name("tokenizer-manifest.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TokenizerContractError(
            "tokenizer-manifest.json is missing or invalid"
        ) from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise TokenizerContractError("unsupported tokenizer manifest schema")
    if manifest.get("tokenizer_id") != tokenizer_id:
        raise TokenizerContractError(
            "tokenizer code and manifest declare different tokenizer IDs"
        )
    return LoadedTokenizer(tokenizer_id=tokenizer_id, tokenize=tokenize)


@lru_cache(maxsize=1)
def _selected_tokenizer() -> LoadedTokenizer:
    return _load_from_module(import_module("tokenizer_impl.tokenizer"))


def load_tokenizer(*, expected_id: str | None = None) -> LoadedTokenizer:
    """Return the selected tokenizer, rejecting a model/tokenizer mismatch."""

    tokenizer = _selected_tokenizer()
    if expected_id is not None and tokenizer.tokenizer_id != expected_id:
        raise TokenizerContractError(
            "model expects tokenizer "
            f"{expected_id!r}, but the image contains {tokenizer.tokenizer_id!r}; "
            "retrain/export a matching model or select its original tokenizer"
        )
    return tokenizer
