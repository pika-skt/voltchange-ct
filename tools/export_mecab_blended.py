#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright 2026 voltchange contributors
# SPDX-License-Identifier: Apache-2.0

"""Fit and export the frozen MeCab hybrid-gain heads from public Train."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction import FeatureHasher
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler, normalize

TOKENIZER_ID = "mecab-ko-hybrid-pos-v1"
HASH_BINS = 1_024
RIDGE_ALPHAS = (30.0, 3.0)
TIER_GAIN_WEIGHTS = {
    "fast": (0.60, 0.075),
    "balanced": (0.50, 0.25),
    "premium": (0.20, 0.15),
}
TIER_SAFETY_RATIOS = {
    "fast": 0.9108333333333334,
    "balanced": 0.8916666666666666,
    "premium": 0.9,
}
MODEL_IDS = ("ax31-light", "ax31", "axk1-think")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab-root", type=Path, required=True)
    parser.add_argument("--challenge-root", type=Path, required=True)
    parser.add_argument("--materialized-root", type=Path, required=True)
    parser.add_argument("--official-artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _install_lab_imports(lab_root: Path) -> None:
    sys.path.insert(0, str(lab_root / "src"))
    sys.path.insert(0, str(lab_root / "experiments"))


def main() -> None:
    args = _parser().parse_args()
    lab_root = args.lab_root.resolve()
    _install_lab_imports(lab_root)

    from router_lab.strategies.hybrid_tokenizer import STRUCTURAL_FEATURE_NAMES
    from tokenizer_license_ablation import MecabTokenizer, _features

    from router_lab import load_dataset
    from router_lab.strategies.hashed_ngram import _training_targets

    train = load_dataset(
        "train",
        challenge_root=args.challenge_root,
        materialized_root=args.materialized_root,
    )
    feature_rows, structural, runtime = _features(
        train.content_episodes,
        MecabTokenizer(),
    )
    hasher = FeatureHasher(
        n_features=HASH_BINS,
        input_type="string",
        alternate_sign=True,
    )
    hashed = normalize(hasher.transform(feature_rows), norm="l2")
    scaler = StandardScaler().fit(structural)
    matrix = hstack(
        (csr_matrix(scaler.transform(structural)), hashed),
        format="csr",
    )
    scores, _input, _output, generation_counts = _training_targets(train)
    gains = scores[:, 1:] - scores[:, :1]
    sample_weight = generation_counts / float(np.mean(generation_counts))
    model = Ridge(
        alpha=np.asarray(RIDGE_ALPHAS),
        solver="lsqr",
    ).fit(matrix, gains, sample_weight=sample_weight)

    coefficient_count = len(STRUCTURAL_FEATURE_NAMES) + HASH_BINS
    if model.coef_.shape != (2, coefficient_count):
        raise RuntimeError(f"unexpected gain coefficient shape: {model.coef_.shape}")
    official_artifact = args.official_artifact.resolve()
    artifact = {
        "artifact_type": "voltchange-mecab-blended-gain-v1",
        "schema_version": 1,
        "feature_version": 1,
        "hash_algorithm": "sklearn-murmurhash3-x86-32-signed-l2-v1",
        "hash_bins": HASH_BINS,
        "structural_feature_names": list(STRUCTURAL_FEATURE_NAMES),
        "model_ids": list(MODEL_IDS),
        "tokenizer_id": TOKENIZER_ID,
        "policy_id": train.policy.policy_id,
        "policy_sha256": train.policy_sha256,
        "official_artifact_sha256": _sha256(official_artifact),
        "structural_mean": scaler.mean_.astype(float).tolist(),
        "structural_scale": scaler.scale_.astype(float).tolist(),
        "gain_heads": {
            "ax31-minus-ax31-light": {
                "intercept": float(model.intercept_[0]),
                "coefficients": model.coef_[0].astype(float).tolist(),
            },
            "axk1-think-minus-ax31-light": {
                "intercept": float(model.intercept_[1]),
                "coefficients": model.coef_[1].astype(float).tolist(),
            },
        },
        "tier_hybrid_gain_weights": {
            tier: list(weights) for tier, weights in TIER_GAIN_WEIGHTS.items()
        },
        "tier_safety_ratios": TIER_SAFETY_RATIOS,
        "training_summary": {
            "episodes": len(train.content_episodes),
            "gain_targets": [
                "ax31-minus-ax31-light",
                "axk1-think-minus-ax31-light",
            ],
            "ridge_alphas": list(RIDGE_ALPHAS),
            "sample_weight": "episode-num-generations-normalized",
            "tokenization_seconds": runtime["tokenization_seconds"],
            "mecab_ko_version": importlib.metadata.version("mecab-ko"),
            "mecab_ko_dic_version": importlib.metadata.version("mecab-ko-dic"),
            "source_commit": "fe300cbc2bede1418f77c6666b636cca9696b4df",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "sha256": _sha256(args.output),
                "coefficient_count_per_head": coefficient_count,
                "tokenization_seconds": runtime["tokenization_seconds"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
