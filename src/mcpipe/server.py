"""MCP stdio server for mcpipe.

Reads newline-delimited JSON-RPC 2.0 from stdin, writes responses to stdout.
All logging goes to stderr (stdout is reserved for the protocol).

Pipeline meta-params (_offset, _limit, _search) are extracted from tool args
before dispatch so any tool can be paginated/searched without knowing about it.
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import asdict
from typing import Any

from mcpipe._version import __appname__, __version__
from mcpipe.bootstrap import bootstrap
from mcpipe.log import get_logger
from mcpipe.plugin import ToolOutput, execute, get_tools
from mcpipe.transform import TransformStep, get_transforms
from mcpipe.types.protocol import (
    ErrorCode,
    InitializeResult,
    ServerCapabilities,
    ServerInfo,
)

_log = get_logger("server")

# Meta-param prefix — stripped from tool args and desugared into transform steps.
_META_PREFIX = "_"


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _camel(name: str) -> str:
    """snake_case → camelCase."""
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _to_json(obj: Any) -> Any:
    """Recursively convert dataclasses/enums to plain dicts for json.dumps."""
    if hasattr(obj, "__dataclass_fields__"):
        return {_camel(k): _to_json(v) for k, v in asdict(obj).items() if v is not None}
    if isinstance(obj, list):
        return [_to_json(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _to_json(v) for k, v in obj.items() if v is not None}
    return obj


def _response(req_id: int | str | None, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": _to_json(result)}


def _error(
    req_id: int | str | None,
    code: ErrorCode,
    message: str,
) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": code.value, "message": message},
    }


# ---------------------------------------------------------------------------
# Request handlers
# ---------------------------------------------------------------------------


def _handle_initialize(req_id: int | str | None) -> dict[str, Any]:
    result = InitializeResult(
        capabilities=ServerCapabilities(),
        server_info=ServerInfo(name=__appname__, version=__version__),
    )
    _log.info("initialize: %s %s", __appname__, __version__)
    return _response(req_id, result)


def _inject_meta_params(schema: dict[str, Any]) -> dict[str, Any]:
    """Add transform meta-params (_search, _limit, etc.) to a tool's input schema.

    Generates from the transform registry — so custom transforms automatically
    appear as meta-params on every plugin tool.
    """
    schema = dict(schema)  # shallow copy
    props = dict(schema.get("properties", {}))

    for name, entry in get_transforms().items():
        param_props = entry.param_schema.get("properties", {})

        if len(param_props) == 1:
            # Single-param transform: expose as _name with that param's type
            param_name = next(iter(param_props))
            param_def = param_props[param_name]
            props[f"_{name}"] = {
                "type": param_def.get("type", "string"),
                "description": f"{entry.description} (transform)",
            }
        elif len(param_props) == 0:
            # No-param transform: expose as _name boolean toggle
            props[f"_{name}"] = {
                "type": "boolean",
                "description": f"{entry.description} (transform)",
            }
        # Multi-param transforms can't be expressed as a single meta-param;
        # use paginate/search framework tools or explicit _name in the future.

    schema["properties"] = props
    return schema


def _handle_tools_list(req_id: int | str | None) -> dict[str, Any]:
    tools = get_tools()
    # Framework tools that shouldn't get meta-params injected
    # (handles/reload are metadata tools, not output tools)
    skip_meta = {
        "handles", "reload",
        "authoring_help", "list_user_extensions", "read_extension",
        "write_plugin", "write_transform",
        "delete_plugin", "delete_transform",
    }
    tool_list = []
    for entry in tools.values():
        t = entry.tool
        input_schema = t.input_schema
        if t.name not in skip_meta:
            input_schema = _inject_meta_params(input_schema)
        tool_def: dict[str, Any] = {
            "name": t.name,
            "description": t.description,
            "inputSchema": input_schema,
        }
        annotations = _to_json(t.annotations)
        if annotations:
            tool_def["annotations"] = annotations
        tool_list.append(tool_def)
    _log.debug("tools/list: returning %d tools", len(tool_list))
    return _response(req_id, {"tools": tool_list})


def _extract_transforms(
    args: dict[str, Any],
) -> tuple[dict[str, Any], list[TransformStep] | None]:
    """Separate _meta transform params from tool args.

    Meta-params prefixed with _ are desugared into transform steps:
      _search="text"  → TransformStep("search", {"pattern": "text"})
      _limit=10       → TransformStep("limit", {"n": 10})
      _offset=5       → TransformStep("offset", {"n": 5})
    """
    tool_args: dict[str, Any] = {}
    steps: list[TransformStep] = []

    for key, value in args.items():
        if key == "_search":
            steps.append(TransformStep("search", {"pattern": str(value)}))
        elif key == "_limit":
            steps.append(TransformStep("limit", {"n": int(value)}))
        elif key == "_offset":
            steps.append(TransformStep("offset", {"n": int(value)}))
        elif key.startswith(_META_PREFIX):
            # Future meta-params: try to interpret as transform
            name = key[len(_META_PREFIX) :]
            steps.append(TransformStep(name, {"_positional": value}))
        else:
            tool_args[key] = value

    return tool_args, steps or None


def _tool_output_to_result(output: ToolOutput) -> dict[str, Any]:
    """Convert ToolOutput to MCP ToolResult dict."""
    content: list[dict[str, str]] = []

    if output.is_inline:
        content.append({"type": "text", "text": output.text or ""})
    else:
        # Large output — return handle + summary
        summary = (
            f"Output cached as '{output.handle}' ({output.total_lines} lines).\n"
            f'Use paginate(handle="{output.handle}") to read, '
            f'or search(handle="{output.handle}", pattern="...") to filter.'
        )
        if output.preview:
            summary += f"\n\nPreview:\n{output.preview}"
        content.append({"type": "text", "text": summary})

    return {"content": content, "isError": output.is_error}


async def _handle_tools_call(
    req_id: int | str | None,
    params: dict[str, Any],
) -> dict[str, Any]:
    name = params.get("name")
    if not name:
        return _error(req_id, ErrorCode.INVALID_PARAMS, "Missing 'name' in tools/call")

    tools = get_tools()
    if name not in tools:
        return _error(
            req_id,
            ErrorCode.INVALID_PARAMS,
            f"Unknown tool: {name}",
        )

    raw_args = params.get("arguments", {})
    tool_args, transforms = _extract_transforms(raw_args)

    _log.info("tools/call: %s", name)
    _log.debug("tool_args=%s transforms=%s", tool_args, transforms)

    try:
        output = await execute(name, tool_args, transforms=transforms)
    except (ValueError, TypeError) as exc:
        return _error(req_id, ErrorCode.INVALID_PARAMS, str(exc))

    result = _tool_output_to_result(output)
    return _response(req_id, result)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

# Methods that are notifications (no response expected).
_NOTIFICATIONS = {"notifications/initialized", "notifications/cancelled"}


async def _dispatch(msg: dict[str, Any]) -> dict[str, Any] | None:
    """Route a JSON-RPC message to the appropriate handler."""
    method = msg.get("method", "")
    req_id = msg.get("id")
    params = msg.get("params", {})

    # Notifications — no response
    if method in _NOTIFICATIONS:
        _log.debug("notification: %s", method)
        return None

    match method:
        case "initialize":
            return _handle_initialize(req_id)
        case "tools/list":
            return _handle_tools_list(req_id)
        case "tools/call":
            return await _handle_tools_call(req_id, params)
        case "ping":
            return _response(req_id, {})
        case _:
            _log.warning("unknown method: %s", method)
            return _error(
                req_id,
                ErrorCode.METHOD_NOT_FOUND,
                f"Unknown method: {method}",
            )


async def serve(*, transport: str = "stdio") -> None:
    """Run the MCP server.

    Args:
        transport: Wire protocol — currently only "stdio" is supported.
    """
    if transport != "stdio":
        raise ValueError(f"Unsupported transport: {transport!r}")

    bootstrap()
    _log.info("MCP server ready (%s %s)", __appname__, __version__)

    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

    loop = asyncio.get_event_loop()
    write_transport, _ = await loop.connect_write_pipe(
        asyncio.streams.FlowControlMixin,
        sys.stdout,
    )
    writer = asyncio.StreamWriter(
        write_transport,
        protocol,
        reader,
        loop,
    )

    while True:
        line = await reader.readline()
        if not line:
            _log.info("stdin closed, shutting down")
            break

        line_str = line.decode("utf-8").strip()
        if not line_str:
            continue

        try:
            msg = json.loads(line_str)
        except json.JSONDecodeError as exc:
            err = _error(None, ErrorCode.PARSE_ERROR, f"Invalid JSON: {exc}")
            writer.write((json.dumps(err) + "\n").encode())
            await writer.drain()
            continue

        response = await _dispatch(msg)
        if response is not None:
            writer.write((json.dumps(response) + "\n").encode())
            await writer.drain()
