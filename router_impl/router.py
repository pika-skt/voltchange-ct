# SPDX-FileCopyrightText: Copyright 2026 voltchange contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen official score/cost heads blended with MeCab hybrid gain heads."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ossp_router.protocol import (
    Episode,
    Message,
    ProtocolError,
    RoutingPolicy,
    policy_sha256,
)
from runtime.contract import ContentEpisode
from runtime.tokenizer import LoadedTokenizer, TokenizerContractError, load_tokenizer

from router_impl.blended_gain import (
    BlendedGainArtifact,
    blend_relative_scores,
    predict_gains,
    select_models,
)
from router_impl.blended_gain import (
    load_artifact as load_gain_artifact,
)
from router_impl.hash_regex import (
    MODEL_IDS,
    HashRegexArtifact,
    load_artifact,
    predict_episode,
)
from router_impl.hybrid_features import episode_text


@dataclass(frozen=True)
class _RouterBundle:
    official_artifact: HashRegexArtifact
    gain_artifact: BlendedGainArtifact
    tokenizer: LoadedTokenizer


_OFFICIAL_TOKEN = re.compile(r"[A-Za-z]+|[가-힣]+|\d+|[^\w\s]", re.UNICODE)


def _official_tokenize(text: str) -> tuple[str, ...]:
    tokens = []
    for token in _OFFICIAL_TOKEN.findall(text):
        normalized = token.casefold()
        if normalized.isdecimal():
            normalized = "<number>"
        tokens.append(normalized)
    return tuple(tokens)


@lru_cache(maxsize=1)
def _bundle() -> _RouterBundle:
    directory = Path(__file__).resolve().parent
    official_path = directory / "hash-regex-public.v1.json"
    gain_path = directory / "mecab-blended-gain.v1.json"
    manifest_path = directory / "artifact-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    official_digest = hashlib.sha256(official_path.read_bytes()).hexdigest()
    gain_digest = hashlib.sha256(gain_path.read_bytes()).hexdigest()
    if manifest.get("official_artifact_sha256") != official_digest:
        raise ProtocolError("official artifact SHA-256 does not match its manifest")
    if manifest.get("gain_artifact_sha256") != gain_digest:
        raise ProtocolError("gain artifact SHA-256 does not match its manifest")
    gain_artifact = load_gain_artifact(gain_path)
    if gain_artifact.official_artifact_sha256 != official_digest:
        raise ProtocolError("gain artifact was trained against another official artifact")
    tokenizer_metadata = manifest.get("tokenizer")
    if not isinstance(tokenizer_metadata, dict):
        raise ProtocolError("router manifest has no tokenizer compatibility metadata")
    expected_tokenizer_id = tokenizer_metadata.get("id")
    if not isinstance(expected_tokenizer_id, str):
        raise ProtocolError("router manifest has an invalid tokenizer ID")
    if expected_tokenizer_id != gain_artifact.tokenizer_id:
        raise ProtocolError("gain artifact and router manifest tokenizer IDs differ")
    try:
        tokenizer = load_tokenizer(expected_id=expected_tokenizer_id)
    except TokenizerContractError as exc:
        raise ProtocolError(str(exc)) from exc
    return _RouterBundle(
        official_artifact=load_artifact(official_path),
        gain_artifact=gain_artifact,
        tokenizer=tokenizer,
    )


def _official_episode(content: ContentEpisode) -> Episode:
    # The placeholder ID is derived from content and is never used by the model.
    if content.source_form == "prompt":
        return Episode(
            episode_id=content.content_key,
            prompt=content.messages[0].content,
        )
    return Episode(
        episode_id=content.content_key,
        messages=tuple(
            Message(role=message.role, content=message.content)
            for message in content.messages
        ),
    )


def route(
    episodes: Sequence[ContentEpisode],
    tier: str,
    policy: RoutingPolicy,
) -> tuple[str, ...]:
    bundle = _bundle()
    official = bundle.official_artifact
    gain = bundle.gain_artifact
    policy_digest = policy_sha256(policy)
    if official.policy_id != policy.policy_id or gain.policy_id != policy.policy_id:
        raise ProtocolError("router artifacts and policy IDs differ")
    if official.policy_digest != policy_digest or gain.policy_digest != policy_digest:
        raise ProtocolError("router artifacts and policy digests differ")
    if not episodes:
        return ()

    official_predictions = [
        predict_episode(
            _official_episode(episode),
            official,
            tokenize=_official_tokenize,
        )
        for episode in episodes
    ]
    hybrid_gains = [
        predict_gains(
            episode,
            bundle.tokenizer(episode_text(episode)),
            gain,
        )
        for episode in episodes
    ]
    scores = [
        blend_relative_scores(
            prediction[0],
            gains,
            gain.tier_hybrid_gain_weights[tier],
        )
        for prediction, gains in zip(official_predictions, hybrid_gains, strict=True)
    ]
    costs = [prediction[1] for prediction in official_predictions]
    selected = select_models(
        scores,
        costs,
        budget_multiplier=float(policy.tiers[tier].budget_multiplier),
        safety_ratio=gain.tier_safety_ratios[tier],
    )
    if any(model_id not in MODEL_IDS for model_id in selected):
        raise ValueError("hash/regex router produced an unknown model ID")
    return selected
