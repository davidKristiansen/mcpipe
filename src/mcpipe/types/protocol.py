"""MCP wire protocol types.

JSON-RPC 2.0 framing, tool definitions, content types, and the
initialize handshake. Only server.py should import from here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# JSON-RPC 2.0
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class JsonRpcRequest:
    method: str
    id: int | str | None = None
    params: dict[str, Any] | None = None
    jsonrpc: str = "2.0"


@dataclass(slots=True)
class JsonRpcResponse:
    id: int | str | None
    result: dict[str, Any] | None = None
    error: JsonRpcError | None = None
    jsonrpc: str = "2.0"


@dataclass(slots=True)
class JsonRpcError:
    code: int
    message: str
    data: Any | None = None


class ErrorCode(int, Enum):
    """Standard JSON-RPC and MCP error codes."""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603


# ---------------------------------------------------------------------------
# Content types (tool results)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class TextContent:
    text: str
    type: str = "text"


@dataclass(slots=True)
class ResourceLink:
    uri: str
    name: str
    description: str | None = None
    mime_type: str | None = None
    type: str = "resource_link"


Content = TextContent | ResourceLink


# ---------------------------------------------------------------------------
# Tool definition and results
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ToolAnnotations:
    """Advisory hints about tool behavior."""

    read_only: bool = False
    destructive: bool = True
    idempotent: bool = False
    open_world: bool = True


@dataclass(slots=True)
class Tool:
    """A tool exposed via MCP."""

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=lambda: {"type": "object"})
    output_schema: dict[str, Any] | None = None
    annotations: ToolAnnotations = field(default_factory=ToolAnnotations)


@dataclass(slots=True)
class ToolResult:
    """Result of a tool invocation."""

    content: list[Content] = field(default_factory=list)
    is_error: bool = False
    structured_content: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Initialize handshake
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ServerCapabilities:
    tools: dict[str, Any] | None = field(default_factory=lambda: {"listChanged": False})


@dataclass(slots=True)
class ServerInfo:
    name: str = "mcpipe"
    version: str = "0.1.0"


@dataclass(slots=True)
class InitializeResult:
    capabilities: ServerCapabilities = field(default_factory=ServerCapabilities)
    server_info: ServerInfo = field(default_factory=ServerInfo)
    protocol_version: str = "2025-06-18"
