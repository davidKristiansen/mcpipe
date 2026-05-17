"""mcpipe — plugin-based MCP server framework.

Plugin authoring surface:

    from mcpipe import tool, Cmd, transform
"""

from mcpipe._version import __appname__, __version__
from mcpipe.bootstrap import bootstrap
from mcpipe.plugin import Cmd, ToolOutput, tool
from mcpipe.transform import TransformStep, transform

__all__ = [
    "__appname__",
    "__version__",
    "bootstrap",
    "tool",
    "transform",
    "Cmd",
    "ToolOutput",
    "TransformStep",
]
