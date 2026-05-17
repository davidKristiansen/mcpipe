"""Sink hints — mcpipe-specific, not part of MCP spec."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SinkPreference(StrEnum):
    """Advisory hint from a plugin about preferred output delivery."""

    STREAM = "stream"  # small output, return inline
    FILE = "file"  # large output, cache to file


@dataclass(slots=True)
class SinkHint:
    prefer: SinkPreference = SinkPreference.STREAM
    cacheable: bool = True
    ttl: int | None = None  # seconds, None = use framework default
