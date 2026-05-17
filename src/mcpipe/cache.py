"""File-based output cache for mcpipe.

Writes tool output to /tmp/mcpipe/, manages handles and TTL-based cleanup.
A handle is a descriptive key like 'git_log_1716000000' that both humans
and LLMs can reason about.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from mcpipe.log import get_logger

CACHE_DIR = Path("/tmp/mcpipe")
DEFAULT_TTL = 3600  # 1 hour

_log = get_logger("cache")


@dataclass(slots=True)
class CachedOutput:
    """A cached output loaded from disk."""

    handle: str
    lines: list[str]
    total_lines: int
    created_at: float

    def slice(self, offset: int = 0, limit: int = 50) -> list[str]:
        return self.lines[offset : offset + limit]

    def search(self, pattern: str) -> list[tuple[int, str]]:
        """Return (line_number, line) pairs matching the regex pattern."""
        regex = re.compile(pattern, re.IGNORECASE)
        return [(i, line) for i, line in enumerate(self.lines) if regex.search(line)]


def _ensure_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def store(tool_name: str, output: str, ttl: int | None = None) -> str:
    """Write output to cache. Returns the handle string."""
    _ensure_dir()
    ts = int(time.time())
    handle = f"{tool_name}_{ts}"
    path = CACHE_DIR / handle
    path.write_text(output, encoding="utf-8")
    # Store TTL as xattr-like sidecar (simple approach)
    meta_path = CACHE_DIR / f"{handle}.meta"
    effective_ttl = ttl if ttl is not None else DEFAULT_TTL
    meta_path.write_text(f"{ts}\n{effective_ttl}\n", encoding="utf-8")
    _log.debug(
        "stored %s (%d bytes, expires in %dm)",
        handle,
        len(output),
        effective_ttl // 60,
    )
    return handle


def load(handle: str) -> CachedOutput:
    """Load cached output by handle. Raises FileNotFoundError if missing."""
    path = CACHE_DIR / handle
    if not path.exists():
        msg = f"No cached output for handle: {handle}"
        raise FileNotFoundError(msg)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    # Read creation time from meta
    meta_path = CACHE_DIR / f"{handle}.meta"
    created_at = 0.0
    if meta_path.exists():
        parts = meta_path.read_text(encoding="utf-8").strip().split("\n")
        created_at = float(parts[0])
    _log.debug("loaded %s (%d lines)", handle, len(lines))
    return CachedOutput(
        handle=handle,
        lines=lines,
        total_lines=len(lines),
        created_at=created_at,
    )


def evict_expired() -> int:
    """Remove expired cache entries. Returns number of entries removed."""
    _ensure_dir()
    now = time.time()
    removed = 0
    for meta_path in CACHE_DIR.glob("*.meta"):
        parts = meta_path.read_text(encoding="utf-8").strip().split("\n")
        if len(parts) < 2:
            continue
        created, ttl = float(parts[0]), int(parts[1])
        if now - created > ttl:
            handle = meta_path.stem
            data_path = CACHE_DIR / handle
            data_path.unlink(missing_ok=True)
            meta_path.unlink(missing_ok=True)
            removed += 1
            _log.debug("evict: removed expired %s", handle)
    if removed:
        _log.info("evict: removed %d expired entries", removed)
    return removed


def list_handles() -> list[str]:
    """Return all active (non-expired) handles."""
    _ensure_dir()
    now = time.time()
    handles: list[str] = []
    for meta_path in sorted(CACHE_DIR.glob("*.meta")):
        parts = meta_path.read_text(encoding="utf-8").strip().split("\n")
        if len(parts) < 2:
            continue
        created, ttl = float(parts[0]), int(parts[1])
        if now - created <= ttl:
            handles.append(meta_path.stem)
    return handles
