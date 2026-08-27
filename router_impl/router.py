# SPDX-FileCopyrightText: Copyright 2026 voltchange contributors
# SPDX-License-Identifier: Apache-2.0

"""Default swappable implementation: the public hash/regex linear router."""

from __future__ import annotations

import hashlib
import json
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
from router_impl.hash_regex import (
    MODEL_IDS,
    PREMIUM_AX31_FILL_SAFETY_RATIO,
    HashRegexArtifact,
    fill_ax31_upgrades,
    load_artifact,
    predict_episode,
    select_models,
)
from runtime.contract import ContentEpisode
from runtime.tokenizer import LoadedTokenizer, TokenizerContractError, load_tokenizer


@dataclass(frozen=True)
class _RouterBundle:
    artifact: HashRegexArtifact
    tokenizer: LoadedTokenizer


@lru_cache(maxsize=1)
def _bundle() -> _RouterBundle:
    directory = Path(__file__).resolve().parent
    artifact_path = directory / "hash-regex-public.v1.json"
    manifest_path = directory / "artifact-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = manifest.get("artifact_sha256")
    actual = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    if expected != actual:
        raise ProtocolError("router artifact SHA-256 does not match its manifest")
    tokenizer_metadata = manifest.get("tokenizer")
    if not isinstance(tokenizer_metadata, dict):
        raise ProtocolError("router manifest has no tokenizer compatibility metadata")
    expected_tokenizer_id = tokenizer_metadata.get("id")
    if not isinstance(expected_tokenizer_id, str):
        raise ProtocolError("router manifest has an invalid tokenizer ID")
    try:
        tokenizer = load_tokenizer(expected_id=expected_tokenizer_id)
    except TokenizerContractError as exc:
        raise ProtocolError(str(exc)) from exc
    return _RouterBundle(artifact=load_artifact(artifact_path), tokenizer=tokenizer)


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
    artifact = bundle.artifact
    if artifact.policy_id != policy.policy_id:
        raise ProtocolError("router artifact and policy IDs differ")
    if artifact.policy_digest != policy_sha256(policy):
        raise ProtocolError("router artifact and policy digests differ")
    if not episodes:
        return ()

    predictions = [
        predict_episode(_official_episode(episode), artifact, tokenize=bundle.tokenizer)
        for episode in episodes
    ]
    scores = [prediction[0] for prediction in predictions]
    costs = [prediction[1] for prediction in predictions]
    selected, _predicted_ratio = select_models(
        scores,
        costs,
        budget_multiplier=float(policy.tiers[tier].budget_multiplier),
        safety_ratio=artifact.tier_safety_ratios[tier],
    )
    if tier == "premium":
        selected, _predicted_ratio = fill_ax31_upgrades(
            selected,
            scores,
            costs,
            budget_multiplier=float(policy.tiers[tier].budget_multiplier),
            safety_ratio=PREMIUM_AX31_FILL_SAFETY_RATIO,
        )
    if any(model_id not in MODEL_IDS for model_id in selected):
        raise ValueError("hash/regex router produced an unknown model ID")
    return selected
