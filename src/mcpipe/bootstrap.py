"""Auto-discover and import all plugins and transforms.

Both CLI and MCP server call bootstrap() once at startup to populate
the tool and transform registries. reload_plugins() re-imports changed
modules without restarting the server.

Discovery order:
  1. Built-in: mcpipe/plugins/ and mcpipe/transforms/
  2. User: $XDG_CONFIG_HOME/mcpipe/plugins/ and transforms/
"""

from __future__ import annotations

import importlib
import importlib.util
import pkgutil
import sys
from pathlib import Path
from types import ModuleType

import mcpipe.plugins as _plugins_pkg
import mcpipe.transforms as _transforms_pkg
from mcpipe.cache import evict_expired
from mcpipe.config import user_plugins_dir, user_transforms_dir
from mcpipe.log import get_logger
from mcpipe.plugin import _clear_plugin_tools, get_tools
from mcpipe.transform import _clear_transforms, get_transforms

# Import framework modules to trigger @tool registration at import time.
__import__("mcpipe.framework")
__import__("mcpipe.authoring")

_log = get_logger("bootstrap")

# Track imported plugin/transform modules for reload.
_loaded_modules: dict[str, ModuleType] = {}


def _discover_and_load(
    package: ModuleType,
    prefix: str,
    *,
    reload: bool = False,
) -> list[str]:
    """Import (or reload) all submodules of a package.

    Returns list of loaded module names.
    """
    loaded: list[str] = []
    for info in pkgutil.iter_modules(package.__path__):
        fqn = f"{prefix}.{info.name}"
        if reload and fqn in _loaded_modules:
            importlib.reload(_loaded_modules[fqn])
            _log.info("reloaded: %s", fqn)
        else:
            mod = importlib.import_module(fqn)
            _loaded_modules[fqn] = mod
            _log.info("loaded: %s", fqn)
        loaded.append(info.name)
    return loaded


def _discover_user_dir(
    directory: Path,
    prefix: str,
    *,
    reload: bool = False,
) -> list[str]:
    """Import .py files from a user directory (not a package).

    Uses importlib.util.spec_from_file_location so the files don't
    need to be part of an installed package.

    Returns list of loaded module names.
    """
    if not directory.is_dir():
        return []

    loaded: list[str] = []
    for py_file in sorted(directory.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        name = py_file.stem
        fqn = f"{prefix}.{name}"

        spec = importlib.util.spec_from_file_location(fqn, py_file)
        if spec is None or spec.loader is None:
            _log.warning("skipped (bad spec): %s", py_file)
            continue
        mod = importlib.util.module_from_spec(spec)
        sys.modules[fqn] = mod
        try:
            spec.loader.exec_module(mod)
        except Exception:
            sys.modules.pop(fqn, None)
            _log.exception("failed to load: %s", py_file)
            continue
        _loaded_modules[fqn] = mod
        action = "reloaded" if reload else "loaded"
        _log.info("%s (user): %s", action, fqn)
        loaded.append(name)
    return loaded


def bootstrap() -> None:
    """Import all plugins and transforms, triggering registration."""
    evict_expired()

    # Built-in transforms, then user transforms
    _discover_and_load(_transforms_pkg, "mcpipe.transforms")
    _discover_user_dir(user_transforms_dir(), "mcpipe_user.transforms")
    _log.info("transforms registered: %d", len(get_transforms()))

    # Built-in plugins, then user plugins
    _discover_and_load(_plugins_pkg, "mcpipe.plugins")
    _discover_user_dir(user_plugins_dir(), "mcpipe_user.plugins")
    _log.info("total tools registered: %d", len(get_tools()))


def reload_plugins() -> dict[str, list[str]]:
    """Reload all plugin and transform modules.

    Clears plugin tools and transforms, then re-imports everything.
    Framework tools (view, handles, reload) are preserved.

    Returns a summary: {"tools": [...], "transforms": [...]}.
    """
    old_tools = set(get_tools().keys())
    old_transforms = set(get_transforms().keys())

    _clear_plugin_tools()
    _clear_transforms()

    # Built-in
    _discover_and_load(
        _transforms_pkg, "mcpipe.transforms", reload=True,
    )
    _discover_and_load(
        _plugins_pkg, "mcpipe.plugins", reload=True,
    )

    # User
    _discover_user_dir(
        user_transforms_dir(), "mcpipe_user.transforms", reload=True,
    )
    _discover_user_dir(
        user_plugins_dir(), "mcpipe_user.plugins", reload=True,
    )

    new_tools = set(get_tools().keys())
    new_transforms = set(get_transforms().keys())

    added_tools = sorted(new_tools - old_tools)
    removed_tools = sorted(old_tools - new_tools)
    added_transforms = sorted(new_transforms - old_transforms)
    removed_transforms = sorted(old_transforms - new_transforms)

    _log.info(
        "reload complete: %d tools (%+d), %d transforms (%+d)",
        len(new_tools),
        len(added_tools) - len(removed_tools),
        len(new_transforms),
        len(added_transforms) - len(removed_transforms),
    )

    return {
        "tools": sorted(new_tools),
        "transforms": sorted(new_transforms),
        "added_tools": added_tools,
        "removed_tools": removed_tools,
        "added_transforms": added_transforms,
        "removed_transforms": removed_transforms,
    }
