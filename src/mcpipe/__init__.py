"""mcpipe — plugin-based MCP server framework.

Plugin authoring surface:

    from mcpipe import tool, Cmd, SinkPreference
"""

from mcpipe._version import __appname__, __version__
from mcpipe.bootstrap import bootstrap
from mcpipe.plugin import Cmd, ToolOutput, tool
from mcpipe.types import SinkPreference

__all__ = [
    "__appname__",
    "__version__",
    "bootstrap",
    "tool",
    "Cmd",
    "ToolOutput",
    "SinkPreference",
]
