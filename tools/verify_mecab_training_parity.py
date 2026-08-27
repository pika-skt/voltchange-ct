#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright 2026 voltchange contributors
# SPDX-License-Identifier: Apache-2.0

"""Compare submission MeCab features with the frozen training implementation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from sklearn.feature_extraction import FeatureHasher
from sklearn.preprocessing import normalize


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab-root", type=Path, required=True)
    parser.add_argument("--challenge-root", type=Path, required=True)
    parser.add_argument("--materialized-root", type=Path, required=True)
    parser.add_argument("--split", choices=("train", "dev"), default="dev")
    return parser


def main() -> None:
    args = _parser().parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(args.lab_root / "src"))
    sys.path.insert(0, str(args.lab_root / "experiments"))
    from router_lab.strategies.hybrid_tokenizer import (
        hybrid_token_features as training_features,
    )
    from router_lab.strategies.hybrid_tokenizer import (
        structural_features as training_structural,
    )
    from tokenizer_license_ablation import MecabTokenizer

    from router_lab import load_dataset

    bundle = load_dataset(
        args.split,
        challenge_root=args.challenge_root,
        materialized_root=args.materialized_root,
        allow_dev=args.split == "dev",
    )
    sys.path.insert(0, str(root))
    from router_impl.blended_gain import hashed_feature_vector
    from router_impl.hybrid_features import (
        episode_text,
        hybrid_token_features,
        structural_features,
    )
    from tokenizer_impl.tokenizer import tokenize

    training_tokenizer = MecabTokenizer()
    hasher = FeatureHasher(
        n_features=1_024,
        input_type="string",
        alternate_sign=True,
    )
    for index, episode in enumerate(bundle.content_episodes):
        text = episode_text(episode)
        training_tokens = training_tokenizer(text)
        runtime_tokens = tokenize(text)
        expected_tokens = tuple(f"{token.tag}\t{token.form}" for token in training_tokens)
        if runtime_tokens != expected_tokens:
            raise AssertionError(f"token mismatch at row {index}")
        expected_features = training_features(training_tokens)
        actual_features = hybrid_token_features(runtime_tokens)
        if actual_features != expected_features:
            raise AssertionError(f"feature mismatch at row {index}")
        np.testing.assert_array_equal(
            np.asarray(hashed_feature_vector(actual_features, 1_024)),
            normalize(hasher.transform([expected_features]), norm="l2").toarray()[0],
        )
        np.testing.assert_array_equal(
            np.asarray(structural_features(episode)),
            np.asarray(training_structural(episode)),
        )
    print(f"OK: {len(bundle.content_episodes)} {args.split} rows match training")


if __name__ == "__main__":
    main()
