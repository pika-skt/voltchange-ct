# SPDX-FileCopyrightText: Copyright 2026 voltchange contributors
# SPDX-License-Identifier: Apache-2.0

"""Bridge the official wire protocol to a content-only router plugin."""

from __future__ import annotations

from collections.abc import Sequence
from importlib import import_module

from ossp_router.protocol import (
    MODEL_IDS,
    TIERS,
    Decision,
    InputBatch,
    ProtocolError,
    RoutingPolicy,
    Submission,
    parse_submission,
    submission_to_dict,
)
from runtime.contract import (
    ContentEpisode,
    RouteFunction,
    canonical_content_json,
    content_episode_from_official,
)


class RouterContractError(ValueError):
    """Raised when a swappable router violates the runtime contract."""


def load_route_function() -> RouteFunction:
    module = import_module("router_impl.router")
    route = getattr(module, "route", None)
    if not callable(route):
        raise RouterContractError(
            "router_impl.router must export callable route(episodes, tier, policy)"
        )
    return route


def _validated_choices(result: Sequence[str], expected: int) -> tuple[str, ...]:
    if isinstance(result, (str, bytes)):
        raise RouterContractError("route() must return a sequence of model IDs")
    try:
        choices = tuple(result)
    except TypeError as exc:
        raise RouterContractError(
            "route() must return an iterable of model IDs"
        ) from exc
    if len(choices) != expected:
        raise RouterContractError(
            f"route() returned {len(choices)} choices for {expected} prompts"
        )
    invalid = sorted(
        {
            repr(choice)
            for choice in choices
            if not isinstance(choice, str) or choice not in MODEL_IDS
        }
    )
    if invalid:
        raise RouterContractError(f"route() returned unknown model IDs: {invalid}")
    return choices


def make_submission(
    inputs: InputBatch,
    policy: RoutingPolicy,
    tier: str,
    *,
    route_function: RouteFunction | None = None,
) -> Submission:
    """Route a batch without exposing IDs, split, or input order to the plugin."""

    if inputs.schema_version != policy.schema_version:
        raise ProtocolError("input and policy schema versions differ")
    if tier not in TIERS:
        raise ProtocolError(f"unknown tier: {tier}")

    indexed: list[tuple[int, ContentEpisode]] = [
        (position, content_episode_from_official(episode))
        for position, episode in enumerate(inputs.episodes)
    ]
    # Sorting by prompt content makes the plugin boundary independent of evaluator
    # input order. The original positions are retained only by this adapter.
    ordered = sorted(
        indexed,
        key=lambda item: (
            item[1].content_key,
            canonical_content_json(item[1].messages),
        ),
    )
    route = route_function or load_route_function()
    choices = _validated_choices(
        route(tuple(content for _position, content in ordered), tier, policy),
        len(ordered),
    )

    by_position: list[str | None] = [None] * len(indexed)
    choice_by_content: dict[str, str] = {}
    for (position, content), choice in zip(ordered, choices, strict=True):
        canonical = canonical_content_json(content.messages)
        previous = choice_by_content.setdefault(canonical, choice)
        if previous != choice:
            raise RouterContractError(
                "route() selected different models for identical prompt content"
            )
        by_position[position] = choice
    if any(choice is None for choice in by_position):
        raise RouterContractError("route() did not produce a complete decision set")
    complete_choices = tuple(choice for choice in by_position if choice is not None)

    submission = Submission(
        schema_version=inputs.schema_version,
        challenge_id=inputs.challenge_id,
        policy_id=policy.policy_id,
        split=inputs.split,
        tier=tier,
        decisions=tuple(
            Decision(episode.episode_id, choice)
            for episode, choice in zip(inputs.episodes, complete_choices, strict=True)
        ),
    )
    return parse_submission(submission_to_dict(submission))
