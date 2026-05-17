"""User config directory resolution.

Follows XDG Base Directory Specification:
  $XDG_CONFIG_HOME/mcpipe/  (default: ~/.config/mcpipe/)

Layout:
  plugins/     — user-authored plugin .py files
  transforms/  — user-authored transform .py files
"""

from __future__ import annotations

import os
from pathlib import Path


def config_home() -> Path:
    """Return the mcpipe config root directory."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        base = Path(xdg)
    else:
        base = Path.home() / ".config"
    return base / "mcpipe"


def user_plugins_dir() -> Path:
    return config_home() / "plugins"


def user_transforms_dir() -> Path:
    return config_home() / "transforms"


def ensure_user_dirs() -> None:
    """Create user plugin/transform directories if they don't exist."""
    user_plugins_dir().mkdir(parents=True, exist_ok=True)
    user_transforms_dir().mkdir(parents=True, exist_ok=True)
