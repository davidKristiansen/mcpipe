"""Plugin API for mcpipe.

The entire plugin authoring surface:
- @tool decorator: registers a function as an MCP tool
- Cmd: return this to run a subprocess
- Return str for direct output
"""

from __future__ import annotations

import asyncio
import inspect
import typing
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, get_type_hints

from mcpipe.log import get_logger
from mcpipe.types._hints import SinkHint, SinkPreference
from mcpipe.types.protocol import Tool, ToolAnnotations

_log = get_logger("plugin")

# ---------------------------------------------------------------------------
# Cmd — "run this as a subprocess"
# ---------------------------------------------------------------------------

# Threshold (in lines) above which output is always cached.
INLINE_THRESHOLD = 50


@dataclass(slots=True)
class Cmd:
    """Return from a @tool function to run a subprocess."""

    argv: list[str]

    def __init__(self, *args: str):
        self.argv = list(args)


@dataclass(slots=True)
class ToolOutput:
    """Structured result from execute().

    If the output was cached, `handle` is set and `preview` contains the
    first few lines. If inline, `text` contains the full output.
    """

    handle: str | None = None
    text: str | None = None
    preview: str = ""
    total_lines: int = 0
    is_error: bool = False

    @property
    def is_cached(self) -> bool:
        return self.handle is not None


# ---------------------------------------------------------------------------
# Registry — all discovered tools
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, _ToolEntry] = {}


@dataclass(slots=True)
class _ToolEntry:
    func: Callable[..., Cmd | str]
    tool: Tool
    sink_hint: SinkHint
    plugin: str


def get_tools() -> dict[str, _ToolEntry]:
    return _REGISTRY


# ---------------------------------------------------------------------------
# @tool decorator
# ---------------------------------------------------------------------------

_PY_TO_JSON: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def _build_schema(func: Callable) -> dict[str, Any]:
    """Generate JSON Schema from function signature + type hints."""
    hints = get_type_hints(func, include_extras=True)
    sig = inspect.signature(func)
    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, param in sig.parameters.items():
        hint = hints.get(name, str)
        description = None

        # Unwrap Annotated[type, "description"]
        origin = typing.get_origin(hint)
        if origin is Annotated:
            args = typing.get_args(hint)
            hint = args[0]
            for meta in args[1:]:
                if isinstance(meta, str):
                    description = meta
                    break

        json_type = _PY_TO_JSON.get(hint, "string")
        prop: dict[str, Any] = {"type": json_type}
        if description:
            prop["description"] = description
        if param.default is not inspect.Parameter.empty:
            prop["default"] = param.default
        else:
            required.append(name)

        properties[name] = prop

    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _caller_plugin_name() -> str:
    """Derive plugin name from the calling module.

    If the caller is mcpipe.plugins.git, returns 'git'.
    Falls back to the bare module name.
    """
    frame = inspect.stack()[2]  # [0]=this, [1]=tool(), [2]=caller
    module = frame.frame.f_globals.get("__name__", "")
    # mcpipe.plugins.git -> git
    if module.startswith("mcpipe.plugins."):
        return module.rsplit(".", 1)[-1]
    return module.rsplit(".", 1)[-1]


def tool(
    description: str,
    *,
    read_only: bool = False,
    destructive: bool = True,
    idempotent: bool = False,
    open_world: bool = True,
    sink: SinkPreference = SinkPreference.STREAM,
    ttl: int | None = None,
) -> Callable:
    """Register a function as an mcpipe tool.

    The function name becomes the MCP tool name.
    Type hints generate the input schema.
    Return Cmd for subprocess, str for direct output.
    """
    plugin_name = _caller_plugin_name()

    def decorator[F: Callable[..., Cmd | str]](func: F) -> F:
        name: str = getattr(func, "__name__")  # noqa: B009
        schema = _build_schema(func)

        entry = _ToolEntry(
            func=func,
            tool=Tool(
                name=name,
                description=description,
                input_schema=schema,
                annotations=ToolAnnotations(
                    read_only=read_only,
                    destructive=destructive,
                    idempotent=idempotent,
                    open_world=open_world,
                ),
            ),
            sink_hint=SinkHint(prefer=sink, ttl=ttl),
            plugin=plugin_name,
        )
        _REGISTRY[name] = entry
        return func

    return decorator


# ---------------------------------------------------------------------------
# execute — run a tool by name, cache if needed
# ---------------------------------------------------------------------------

_PREVIEW_LINES = 5


def _make_preview(output: str, max_lines: int = _PREVIEW_LINES) -> str:
    lines = output.splitlines()[:max_lines]
    return "\n".join(lines)


async def _run_func(entry: _ToolEntry, args: dict[str, Any]) -> str:
    """Run the tool function, handling both Cmd and str returns."""
    result = entry.func(**args)

    if isinstance(result, Cmd):
        proc = await asyncio.create_subprocess_exec(
            *result.argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            msg = f"Error (exit {proc.returncode}):\n{stderr.decode(errors='replace')}"
            raise RuntimeError(msg)
        return stdout.decode(errors="replace")

    if isinstance(result, str):
        return result

    raise TypeError(f"Tool returned unexpected type: {type(result)}")


async def execute(tool_name: str, args: dict[str, Any]) -> ToolOutput:
    """Look up a tool, execute it, and route output through cache if needed."""
    from mcpipe.cache import store  # deferred to avoid circular import

    entry = _REGISTRY.get(tool_name)
    if entry is None:
        raise ValueError(f"Unknown tool: {tool_name}")

    _log.info("executing %s", tool_name)
    _log.debug("args: %s", args)

    try:
        output = await _run_func(entry, args)
    except RuntimeError as exc:
        _log.warning("tool %s failed: %s", tool_name, exc)
        return ToolOutput(text=str(exc), is_error=True)

    line_count = output.count("\n") + (1 if output and not output.endswith("\n") else 0)
    should_cache = (
        entry.sink_hint.prefer == SinkPreference.FILE or line_count > INLINE_THRESHOLD
    )

    _log.debug(
        "%s: %d lines, hint=%s, caching=%s",
        tool_name, line_count, entry.sink_hint.prefer, should_cache,
    )

    if should_cache:
        handle = store(tool_name, output, ttl=entry.sink_hint.ttl)
        _log.info("cached %s -> %s", tool_name, handle)
        return ToolOutput(
            handle=handle,
            preview=_make_preview(output),
            total_lines=line_count,
        )

    return ToolOutput(text=output, total_lines=line_count)
