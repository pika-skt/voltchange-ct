# SPDX-FileCopyrightText: Copyright 2026 voltchange contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import json
import stat
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from examples.always_light.router import route as always_light_route
from ossp_router.protocol import (
    MODEL_IDS,
    Episode,
    InputBatch,
    load_bundled_policy,
    load_input,
)
from runtime.adapter import RouterContractError, make_submission
from runtime.contract import canonical_content_json, content_episode_from_official
from runtime.entrypoint import main
from runtime.tokenizer import TokenizerContractError, load_tokenizer
from tools.source_manifest import build_manifest

ROOT = Path(__file__).resolve().parents[1]
TOY_INPUT = ROOT / "tests" / "data" / "toy-inputs.json"


class RuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inputs = load_input(TOY_INPUT)
        self.policy = load_bundled_policy()

    def test_default_router_matches_frozen_test_vector(self) -> None:
        vector = json.loads((ROOT / "test-vector.json").read_text(encoding="utf-8"))
        self.assertEqual(
            hashlib.sha256(TOY_INPUT.read_bytes()).hexdigest(),
            vector["input_sha256"],
        )
        actual = {}
        for tier in ("fast", "balanced", "premium"):
            submission = make_submission(self.inputs, self.policy, tier)
            actual[tier] = [decision.model_id for decision in submission.decisions]
        self.assertEqual(actual, vector["expected_model_ids"])

    def test_adapter_hides_ids_and_canonicalizes_order(self) -> None:
        observed = []

        def inspecting_route(episodes, tier, policy):
            self.assertEqual(tier, "fast")
            self.assertEqual(policy.policy_id, self.policy.policy_id)
            self.assertTrue(all(not hasattr(item, "episode_id") for item in episodes))
            observed.extend(item.content_key for item in episodes)
            return tuple(policy.light_model_id for _item in episodes)

        submission = make_submission(
            self.inputs,
            self.policy,
            "fast",
            route_function=inspecting_route,
        )

        self.assertEqual(observed, sorted(observed))
        self.assertEqual(
            [decision.episode_id for decision in submission.decisions],
            [episode.episode_id for episode in self.inputs.episodes],
        )

    def test_default_router_is_id_and_order_independent(self) -> None:
        original = make_submission(self.inputs, self.policy, "premium")
        reversed_episodes = tuple(
            replace(episode, episode_id=f"audit-{position}")
            for position, episode in enumerate(reversed(self.inputs.episodes))
        )
        audited_inputs = InputBatch(
            schema_version=self.inputs.schema_version,
            challenge_id="changed-challenge-id",
            split="changed-split",
            episodes=reversed_episodes,
        )
        audited = make_submission(audited_inputs, self.policy, "premium")

        original_by_content = {
            canonical_content_json(
                content_episode_from_official(episode).messages
            ): decision.model_id
            for episode, decision in zip(
                self.inputs.episodes, original.decisions, strict=True
            )
        }
        audited_by_content = {
            canonical_content_json(
                content_episode_from_official(episode).messages
            ): decision.model_id
            for episode, decision in zip(
                audited_inputs.episodes, audited.decisions, strict=True
            )
        }
        self.assertEqual(original_by_content, audited_by_content)

    def test_duplicate_content_must_have_one_choice(self) -> None:
        duplicate = Episode(episode_id="duplicate", prompt="same prompt")
        inputs = InputBatch(
            1, "challenge", "test", (duplicate, replace(duplicate, episode_id="other"))
        )

        def disagreeing_route(episodes, tier, policy):
            del episodes, tier, policy
            return (MODEL_IDS[0], MODEL_IDS[1])

        with self.assertRaisesRegex(RouterContractError, "identical prompt"):
            make_submission(
                inputs,
                self.policy,
                "fast",
                route_function=disagreeing_route,
            )

    def test_invalid_plugin_output_is_rejected(self) -> None:
        def invalid_route(episodes, tier, policy):
            del tier, policy
            return tuple("not-a-model" for _episode in episodes)

        with self.assertRaisesRegex(RouterContractError, "unknown model"):
            make_submission(
                self.inputs,
                self.policy,
                "fast",
                route_function=invalid_route,
            )

    def test_unhashable_plugin_output_is_rejected_cleanly(self) -> None:
        def invalid_route(episodes, tier, policy):
            del tier, policy
            return tuple([] for _episode in episodes)

        with self.assertRaisesRegex(RouterContractError, "unknown model"):
            make_submission(
                self.inputs,
                self.policy,
                "fast",
                route_function=invalid_route,
            )

    def test_always_light_example_uses_the_same_contract(self) -> None:
        submission = make_submission(
            self.inputs,
            self.policy,
            "premium",
            route_function=always_light_route,
        )
        self.assertEqual(
            {decision.model_id for decision in submission.decisions},
            {self.policy.light_model_id},
        )

    def test_cli_leaves_one_atomic_mode_0644_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "submission.json"
            exit_code = main(
                [
                    "--input",
                    str(TOY_INPUT),
                    "--tier",
                    "balanced",
                    "--output",
                    str(output),
                ]
            )
            self.assertEqual(exit_code, 0)
            self.assertEqual(
                [path.name for path in Path(directory).iterdir()], ["submission.json"]
            )
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o644)

    def test_artifact_digest_matches_both_manifests(self) -> None:
        artifact = ROOT / "router_impl" / "hash-regex-public.v1.json"
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        root_manifest = json.loads(
            (ROOT / "artifact-manifest.json").read_text(encoding="utf-8")
        )
        plugin_manifest = json.loads(
            (ROOT / "router_impl" / "artifact-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(digest, root_manifest["artifact_sha256"])
        self.assertEqual(digest, plugin_manifest["artifact_sha256"])
        self.assertEqual(root_manifest["tokenizer"]["id"], "regex-casefold-number-v1")
        self.assertEqual(plugin_manifest["tokenizer"]["id"], "regex-casefold-number-v1")

    def test_default_tokenizer_contract_and_frozen_semantics(self) -> None:
        tokenizer = load_tokenizer(expected_id="regex-casefold-number-v1")
        self.assertEqual(
            tokenizer("Hello, 세계 123!"),
            ("hello", ",", "세계", "<number>", "!"),
        )

    def test_incompatible_tokenizer_is_rejected_before_prediction(self) -> None:
        with self.assertRaisesRegex(
            TokenizerContractError, "retrain/export a matching model"
        ):
            load_tokenizer(expected_id="whitespace-casefold-number-v1")

    def test_source_manifest_binds_selected_tokenizer(self) -> None:
        manifest = build_manifest("router_impl", "tokenizer_impl")
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(manifest["tokenizer"], "tokenizer_impl")
        paths = {entry["path"] for entry in manifest["files"]}
        self.assertIn("tokenizer_impl/tokenizer.py", paths)
        self.assertIn("tokenizer_impl/tokenizer-manifest.json", paths)

    def test_dockerfile_encodes_the_submission_boundary(self) -> None:
        source = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("linux/arm64", (ROOT / "README.md").read_text(encoding="utf-8"))
        self.assertIn("@sha256:", source)
        self.assertIn("ARG ROUTER_IMPL=router_impl", source)
        self.assertIn("ARG TOKENIZER_IMPL=tokenizer_impl", source)
        self.assertIn(
            "${TOKENIZER_IMPL}/ /opt/router/tokenizer_impl/",
            source,
        )
        self.assertNotIn("SOURCE_MANIFEST_SHA256=unbound", source)
        self.assertIn("--require-hashes", source)
        self.assertIn("USER 65532:65532", source)
        self.assertIn('ENTRYPOINT ["python3", "-m", "runtime.entrypoint"]', source)
        self.assertFalse(
            any(
                line.lstrip().upper().startswith("VOLUME")
                for line in source.splitlines()
            )
        )
        self.assertNotIn(
            "kiwipiepy",
            (ROOT / "router_impl" / "requirements.txt").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
