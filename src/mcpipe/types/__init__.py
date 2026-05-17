"""Public types for mcpipe internals.

Plugin authors should import from the top-level package instead:

    from mcpipe import tool, Cmd, SinkPreference
"""

from mcpipe.types._hints import SinkHint, SinkPreference
from mcpipe.types.protocol import ToolAnnotations

__all__ = [
    "SinkHint",
    "SinkPreference",
    "ToolAnnotations",
]
