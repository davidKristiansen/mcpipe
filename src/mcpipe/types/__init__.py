"""Public types for mcpipe internals.

Plugin authors should import from the top-level package instead:

    from mcpipe import tool, Cmd
"""

from mcpipe.types.protocol import ToolAnnotations

__all__ = [
    "ToolAnnotations",
]
