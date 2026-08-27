# SPDX-FileCopyrightText: Copyright 2026 voltchange contributors
# SPDX-License-Identifier: Apache-2.0

"""Minimal implementation used to verify the build-time swap boundary."""

from __future__ import annotations

from collections.abc import Sequence

from ossp_router.protocol import RoutingPolicy
from runtime.contract import ContentEpisode


def route(
    episodes: Sequence[ContentEpisode],
    tier: str,
    policy: RoutingPolicy,
) -> tuple[str, ...]:
    del tier
    return tuple(policy.light_model_id for _episode in episodes)
