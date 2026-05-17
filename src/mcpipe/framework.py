"""Framework tools — built into mcpipe, not in plugins/.

- view: load cached output by handle (transforms do the filtering)
- handles: list active cache handles
- reload: hot-reload plugins and transforms from disk
"""

from __future__ import annotations

import json
from typing import Annotated

from mcpipe.cache import list_handles, load
from mcpipe.log import get_logger
from mcpipe.plugin import tool

_log = get_logger("framework")


@tool(
    "Print cached output by handle. Use transform meta-params "
    "(_offset, _limit, _search, _head, _tail) to filter.",
    read_only=True,
    destructive=False,
    idempotent=True,
)
def view(
    handle: Annotated[str, "Cache handle returned by a previous tool call"],
) -> str:
    try:
        cached = load(handle)
    except FileNotFoundError:
        return f"Error: no cached output for handle '{handle}'"

    _log.debug("view %s (%d lines)", handle, cached.total_lines)
    return "\n".join(cached.lines)


@tool(
    "List all active cache handles",
    read_only=True,
    destructive=False,
    idempotent=True,
)
def handles(
    filter: Annotated[str | None, "Substring filter on handle names"] = None,
) -> str:
    active = list_handles()
    if filter:
        active = [h for h in active if filter in h]
    if not active:
        return "No cached outputs."
    return "\n".join(active)


@tool(
    "Reload all plugins and transforms from disk without restarting",
    read_only=False,
    destructive=False,
    idempotent=True,
)
def reload() -> str:
    from mcpipe.bootstrap import reload_plugins

    summary = reload_plugins()
    return json.dumps(summary, indent=2)
