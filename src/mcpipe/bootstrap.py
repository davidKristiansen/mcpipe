"""Auto-discover and import all plugins under mcpipe.plugins.

Both CLI and MCP server call bootstrap() once at startup to populate
the tool registry. No hardcoded plugin imports needed anywhere.
"""

from __future__ import annotations

import importlib
import pkgutil

import mcpipe.plugins as _plugins_pkg
from mcpipe.log import get_logger

_log = get_logger("bootstrap")


def bootstrap() -> None:
    """Import all plugins and framework tools, triggering @tool registration."""
    # Framework tools (paginate, search, handles)
    import mcpipe.framework  # noqa: F401

    _log.info("framework tools registered")

    # Plugin tools (auto-discovered)
    for info in pkgutil.iter_modules(_plugins_pkg.__path__):
        importlib.import_module(f"mcpipe.plugins.{info.name}")
        _log.info("loaded plugin: %s", info.name)

    from mcpipe.plugin import get_tools

    _log.info("total tools registered: %d", len(get_tools()))
