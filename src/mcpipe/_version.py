"""Package metadata for mcpipe."""

from __future__ import annotations

__version__: str = "0.0.0-dev"
__appname__: str = "mcpipe"

try:
    from importlib.metadata import metadata

    _meta = metadata("mcpipe")
    __version__ = _meta["Version"]
    __appname__ = _meta["Name"]
except Exception:
    pass
