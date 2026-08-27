# SPDX-FileCopyrightText: Copyright 2026 voltchange contributors
# SPDX-License-Identifier: Apache-2.0

"""Content-only types exposed to a router implementation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from ossp_router.protocol import Episode, RoutingPolicy


@dataclass(frozen=True)
class ContentMessage:
    role: str
    content: str


@dataclass(frozen=True)
class ContentEpisode:
    """One prompt with all evaluator identifiers removed."""

    content_key: str
    messages: tuple[ContentMessage, ...]
    source_form: str
    character_count: int
    role_sequence: str


def canonical_content_json(messages: tuple[ContentMessage, ...]) -> str:
    payload = {
        "messages": [
            {"role": message.role, "content": message.content} for message in messages
        ]
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def content_episode_from_official(episode: Episode) -> ContentEpisode:
    if episode.prompt is not None:
        messages = (ContentMessage(role="user", content=episode.prompt),)
        source_form = "prompt"
    else:
        assert episode.messages is not None
        messages = tuple(
            ContentMessage(role=message.role, content=message.content)
            for message in episode.messages
        )
        source_form = "messages"
    canonical = canonical_content_json(messages)
    return ContentEpisode(
        content_key=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        messages=messages,
        source_form=source_form,
        character_count=sum(len(message.content) for message in messages),
        role_sequence=">".join(message.role for message in messages),
    )


class RouteFunction(Protocol):
    def __call__(
        self,
        episodes: Sequence[ContentEpisode],
        tier: str,
        policy: RoutingPolicy,
    ) -> Sequence[str]: ...
