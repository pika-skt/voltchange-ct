# SPDX-FileCopyrightText: Copyright 2026 voltchange contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate and evaluate the frozen MeCab hybrid gain artifact."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import mmh3
from ossp_router.protocol import MODEL_IDS, TIERS, ProtocolError
from runtime.contract import ContentEpisode

from router_impl.hybrid_features import (
    STRUCTURAL_FEATURE_NAMES,
    hybrid_token_features,
    structural_features,
)

ARTIFACT_TYPE = "voltchange-mecab-blended-gain-v1"
HASH_ALGORITHM = "sklearn-murmurhash3-x86-32-signed-l2-v1"
GAIN_NAMES = (
    "ax31-minus-ax31-light",
    "axk1-think-minus-ax31-light",
)


@dataclass(frozen=True)
class LinearHead:
    intercept: float
    coefficients: tuple[float, ...]


@dataclass(frozen=True)
class BlendedGainArtifact:
    hash_bins: int
    tokenizer_id: str
    policy_id: str
    policy_digest: str
    official_artifact_sha256: str
    structural_mean: tuple[float, ...]
    structural_scale: tuple[float, ...]
    gain_heads: Mapping[str, LinearHead]
    tier_hybrid_gain_weights: Mapping[str, tuple[float, float]]
    tier_safety_ratios: Mapping[str, float]
    training_summary: Mapping[str, Any]


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolError(f"{label} must be a JSON object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: Sequence[str], label: str) -> None:
    missing = sorted(set(expected) - set(value))
    extra = sorted(set(value) - set(expected))
    if missing or extra:
        raise ProtocolError(f"{label} fields differ: missing={missing}, extra={extra}")


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProtocolError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ProtocolError(f"{label} must be a finite number")
    return result


def _vector(value: Any, length: int, label: str) -> tuple[float, ...]:
    if not isinstance(value, list) or len(value) != length:
        raise ProtocolError(f"{label} must be an array of length {length}")
    return tuple(_number(item, f"{label}[{index}]") for index, item in enumerate(value))


def _head(value: Any, length: int, label: str) -> LinearHead:
    raw = _object(value, label)
    _exact_keys(raw, ("intercept", "coefficients"), label)
    return LinearHead(
        intercept=_number(raw["intercept"], f"{label}.intercept"),
        coefficients=_vector(raw["coefficients"], length, f"{label}.coefficients"),
    )


def parse_artifact(value: Any) -> BlendedGainArtifact:
    root = _object(value, "gain artifact")
    expected = (
        "artifact_type",
        "schema_version",
        "feature_version",
        "hash_algorithm",
        "hash_bins",
        "structural_feature_names",
        "model_ids",
        "tokenizer_id",
        "policy_id",
        "policy_sha256",
        "official_artifact_sha256",
        "structural_mean",
        "structural_scale",
        "gain_heads",
        "tier_hybrid_gain_weights",
        "tier_safety_ratios",
        "training_summary",
    )
    _exact_keys(root, expected, "gain artifact")
    if root["artifact_type"] != ARTIFACT_TYPE:
        raise ProtocolError("unsupported gain artifact type")
    if root["schema_version"] != 1 or root["feature_version"] != 1:
        raise ProtocolError("unsupported gain artifact version")
    if root["hash_algorithm"] != HASH_ALGORITHM:
        raise ProtocolError("unsupported gain feature hash")
    hash_bins = root["hash_bins"]
    if (
        isinstance(hash_bins, bool)
        or not isinstance(hash_bins, int)
        or not 16 <= hash_bins <= 16_384
        or hash_bins & (hash_bins - 1)
    ):
        raise ProtocolError("gain artifact hash_bins must be a supported power of two")
    if root["structural_feature_names"] != list(STRUCTURAL_FEATURE_NAMES):
        raise ProtocolError("gain artifact structural features differ from runtime")
    if root["model_ids"] != list(MODEL_IDS):
        raise ProtocolError("gain artifact model IDs differ from policy")
    tokenizer_id = root["tokenizer_id"]
    policy_id = root["policy_id"]
    digest = root["policy_sha256"]
    official_digest = root["official_artifact_sha256"]
    if not isinstance(tokenizer_id, str) or not tokenizer_id:
        raise ProtocolError("gain artifact tokenizer ID is invalid")
    if not isinstance(policy_id, str) or not policy_id:
        raise ProtocolError("gain artifact policy ID is invalid")
    if any(
        not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None
        for value in (digest, official_digest)
    ):
        raise ProtocolError("gain artifact SHA-256 field is invalid")
    structural_length = len(STRUCTURAL_FEATURE_NAMES)
    mean = _vector(root["structural_mean"], structural_length, "structural_mean")
    scale = _vector(root["structural_scale"], structural_length, "structural_scale")
    if any(value <= 0 for value in scale):
        raise ProtocolError("gain artifact structural scales must be positive")
    feature_length = structural_length + hash_bins
    heads_raw = _object(root["gain_heads"], "gain_heads")
    if set(heads_raw) != set(GAIN_NAMES):
        raise ProtocolError("gain artifact heads are incomplete")
    weights_raw = _object(
        root["tier_hybrid_gain_weights"], "tier_hybrid_gain_weights"
    )
    safety_raw = _object(root["tier_safety_ratios"], "tier_safety_ratios")
    if set(weights_raw) != set(TIERS) or set(safety_raw) != set(TIERS):
        raise ProtocolError("gain artifact tier configuration is incomplete")
    weights = {tier: _vector(weights_raw[tier], 2, f"weights.{tier}") for tier in TIERS}
    if any(not 0 <= weight <= 1 for pair in weights.values() for weight in pair):
        raise ProtocolError("gain artifact blend weights must be in [0, 1]")
    safety = {tier: _number(safety_raw[tier], f"safety.{tier}") for tier in TIERS}
    if any(not 0 < value <= 1 for value in safety.values()):
        raise ProtocolError("gain artifact safety ratios must be in (0, 1]")
    return BlendedGainArtifact(
        hash_bins=hash_bins,
        tokenizer_id=tokenizer_id,
        policy_id=policy_id,
        policy_digest=digest,
        official_artifact_sha256=official_digest,
        structural_mean=mean,
        structural_scale=scale,
        gain_heads={
            name: _head(heads_raw[name], feature_length, f"gain_heads.{name}")
            for name in GAIN_NAMES
        },
        tier_hybrid_gain_weights=weights,
        tier_safety_ratios=safety,
        training_summary=dict(_object(root["training_summary"], "training_summary")),
    )


def load_artifact(path: Path) -> BlendedGainArtifact:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError("gain artifact is missing or invalid JSON") from exc
    return parse_artifact(value)


def hashed_feature_vector(features: Sequence[str], hash_bins: int) -> tuple[float, ...]:
    bins = [0.0] * hash_bins
    for feature in features:
        hashed = mmh3.hash(feature, 0, signed=True)
        if hashed == -(1 << 31):
            index = ((1 << 31) - 1 - (hash_bins - 1)) % hash_bins
        else:
            index = abs(hashed) % hash_bins
        bins[index] += 1.0 if hashed >= 0 else -1.0
    norm = math.sqrt(math.fsum(value * value for value in bins))
    if norm:
        bins = [value / norm for value in bins]
    return tuple(bins)


def _linear(head: LinearHead, values: Sequence[float]) -> float:
    return head.intercept + math.fsum(
        coefficient * value
        for coefficient, value in zip(head.coefficients, values, strict=True)
    )


def predict_gains(
    episode: ContentEpisode,
    encoded_tokens: Sequence[str],
    artifact: BlendedGainArtifact,
) -> tuple[float, float]:
    structural = structural_features(episode)
    standardized = tuple(
        (value - mean) / scale
        for value, mean, scale in zip(
            structural,
            artifact.structural_mean,
            artifact.structural_scale,
            strict=True,
        )
    )
    hashed = hashed_feature_vector(
        hybrid_token_features(encoded_tokens), artifact.hash_bins
    )
    values = standardized + hashed
    return tuple(_linear(artifact.gain_heads[name], values) for name in GAIN_NAMES)


def blend_relative_scores(
    official_scores: Mapping[str, float],
    hybrid_gains: Sequence[float],
    weights: Sequence[float],
) -> dict[str, float]:
    light, ax31, k1 = MODEL_IDS
    result = {light: 0.0}
    for model_id, hybrid_gain, weight in zip(
        (ax31, k1), hybrid_gains, weights, strict=True
    ):
        official_gain = official_scores[model_id] - official_scores[light]
        result[model_id] = (1.0 - weight) * official_gain + weight * hybrid_gain
    return result


def select_models(
    scores: Sequence[Mapping[str, float]],
    costs: Sequence[Mapping[str, float]],
    *,
    budget_multiplier: float,
    safety_ratio: float,
) -> tuple[str, ...]:
    if len(scores) != len(costs) or not scores:
        raise ValueError("score and cost predictions must be non-empty and aligned")
    def stable_total(values: Sequence[float]) -> float:
        return math.fsum(sorted(values))

    light_total = stable_total([row[MODEL_IDS[0]] for row in costs])
    cap = light_total * max(1.0, budget_multiplier * safety_ratio)

    def choose(penalty: float) -> tuple[tuple[str, ...], float]:
        selected = tuple(
            max(
                MODEL_IDS,
                key=lambda model_id: (
                    row_scores[model_id]
                    - penalty * row_costs[model_id] / light_total,
                    -MODEL_IDS.index(model_id),
                ),
            )
            for row_scores, row_costs in zip(scores, costs, strict=True)
        )
        total = stable_total(
            [row_costs[model_id] for row_costs, model_id in zip(costs, selected)]
        )
        return selected, total

    selected, total = choose(0.0)
    if total > cap:
        low = 0.0
        high = 1.0
        selected, total = choose(high)
        while total > cap and high < 2**60:
            low = high
            high *= 2.0
            selected, total = choose(high)
        for _iteration in range(80):
            middle = (low + high) / 2.0
            candidate, candidate_total = choose(middle)
            if candidate_total <= cap:
                high = middle
                selected, total = candidate, candidate_total
            else:
                low = middle
    if total > cap:
        return tuple(MODEL_IDS[0] for _row in scores)
    return selected
