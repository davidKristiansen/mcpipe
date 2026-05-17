"""Framework tools — generic consumers of cached output.

These are built into mcpipe and work with any plugin's cached output.
They should NOT be in the plugins/ directory since they are framework-level,
not plugin-level, but they register as tools via the same @tool decorator.
"""

from __future__ import annotations

from typing import Annotated

from mcpipe.cache import list_handles, load
from mcpipe.log import get_logger
from mcpipe.plugin import SinkPreference, tool

_log = get_logger("framework")


@tool(
    "Paginate cached output by handle — returns a slice of lines",
    read_only=True,
    destructive=False,
    idempotent=True,
    sink=SinkPreference.STREAM,
)
def paginate(
    handle: Annotated[str, "Cache handle returned by a previous tool call"],
    offset: Annotated[int, "Line offset to start from (0-based)"] = 0,
    limit: Annotated[int, "Maximum number of lines to return"] = 50,
) -> str:
    try:
        cached = load(handle)
    except FileNotFoundError:
        return f"Error: no cached output for handle '{handle}'"
    lines = cached.slice(offset, limit)
    if not lines:
        return f"No lines at offset {offset} (total: {cached.total_lines})"
    _log.debug(
        "paginate %s offset=%d limit=%d -> %d lines",
        handle, offset, limit, len(lines),
    )
    end = offset + len(lines) - 1
    header = f"[{handle}] lines {offset}-{end} of {cached.total_lines}\n"
    return header + "\n".join(lines)


@tool(
    "Search cached output by regex pattern — returns matching lines",
    read_only=True,
    destructive=False,
    idempotent=True,
    sink=SinkPreference.STREAM,
)
def search(
    handle: Annotated[str, "Cache handle returned by a previous tool call"],
    pattern: Annotated[str, "Regex pattern to search for (case-insensitive)"],
) -> str:
    try:
        cached = load(handle)
    except FileNotFoundError:
        return f"Error: no cached output for handle '{handle}'"
    matches = cached.search(pattern)
    if not matches:
        return f"No matches for '{pattern}' in {handle} ({cached.total_lines} lines)"
    _log.debug(
        "search %s pattern=%r -> %d matches",
        handle, pattern, len(matches),
    )
    header = f"[{handle}] {len(matches)} matches for '{pattern}':\n"
    body = "\n".join(f"  {lineno}: {line}" for lineno, line in matches)
    return header + body


@tool(
    "List all active cache handles",
    read_only=True,
    destructive=False,
    idempotent=True,
    sink=SinkPreference.STREAM,
)
def handles() -> str:
    active = list_handles()
    if not active:
        return "No cached outputs."
    return "\n".join(active)
