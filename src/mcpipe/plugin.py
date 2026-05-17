"""Plugin API for mcpipe.

The entire plugin authoring surface:
- @tool decorator: registers a function as an MCP tool
- Cmd: return this to run a subprocess
- Return str for direct output
"""

from __future__ import annotations

import asyncio
import inspect
import os
import typing
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, get_type_hints

from mcpipe.cache import store
from mcpipe.log import get_logger
from mcpipe.transform import TransformStep, apply_transforms
from mcpipe.types.protocol import Tool, ToolAnnotations

_log = get_logger("plugin")

# ---------------------------------------------------------------------------
# Cmd — "run this as a subprocess"
# ---------------------------------------------------------------------------

# Output below this threshold is returned inline (full text in response).
# All output is always cached regardless.
INLINE_THRESHOLD = 50

# Meta-param prefix — pipeline params use this to avoid collision with tool args.
META_PREFIX = "_"


@dataclass(slots=True)
class Cmd:
    """Return from a @tool function to run a subprocess."""

    argv: list[str]

    def __init__(self, *args: str):
        self.argv = list(args)


@dataclass(slots=True)
class ToolOutput:
    """Structured result from execute().

    Every result has a handle (output is always cached).
    Small output also includes `text` with the full content inline.
    Large output includes `preview` with the first few lines.
    """

    handle: str
    total_lines: int = 0
    text: str | None = None
    preview: str | None = None
    is_error: bool = False

    @property
    def is_inline(self) -> bool:
        return self.text is not None


# ---------------------------------------------------------------------------
# Registry — all discovered tools
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, _ToolEntry] = {}


@dataclass(slots=True)
class _ToolEntry:
    func: Callable[..., Cmd | str]
    tool: Tool
    ttl: int | None
    plugin: str


def get_tools() -> dict[str, _ToolEntry]:
    return _REGISTRY


_FRAMEWORK_PLUGINS = frozenset({"framework", "authoring"})


def _clear_plugin_tools() -> set[str]:
    """Remove all plugin-registered tools (not framework tools).

    Returns the set of removed tool names.
    """
    to_remove = {
        name for name, entry in _REGISTRY.items()
        if entry.plugin not in _FRAMEWORK_PLUGINS
    }
    for name in to_remove:
        del _REGISTRY[name]
    return to_remove


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
            ttl=ttl,
            plugin=plugin_name,
        )
        _REGISTRY[name] = entry
        return func

    return decorator


# ---------------------------------------------------------------------------
# execute — run a tool by name, cache if needed
# ---------------------------------------------------------------------------

_PREVIEW_LINES = 5


def _sanitize_args(args: dict[str, Any]) -> dict[str, Any]:
    """Expand ~ and $ENV in string arguments."""
    out: dict[str, Any] = {}
    for key, value in args.items():
        if isinstance(value, str):
            value = os.path.expandvars(os.path.expanduser(value))
        out[key] = value
    return out


def _make_preview(output: str, max_lines: int = _PREVIEW_LINES) -> str:
    lines = output.splitlines()[:max_lines]
    return "\n".join(lines)


async def _run_func(entry: _ToolEntry, args: dict[str, Any]) -> str:
    """Run the tool function, handling both Cmd and str returns."""
    try:
        result = entry.func(**args)
    except TypeError as exc:
        # Turn "got an unexpected keyword argument 'x'" into a clean error
        known = list(entry.tool.input_schema.get("properties", {}).keys())
        raise ValueError(
            f"{exc}. Known args: {', '.join(known) or '(none)'}",
        ) from None

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


async def execute(
    tool_name: str,
    args: dict[str, Any],
    transforms: list[TransformStep] | None = None,
) -> ToolOutput:
    """Look up a tool, execute it, cache output, and return structured result.

    If transforms are provided, they are applied in order after caching.
    Transforms are pure: lines in → lines out. The cache is never mutated.
    """
    entry = _REGISTRY.get(tool_name)
    if entry is None:
        raise ValueError(f"Unknown tool: {tool_name}")

    _log.info("executing %s", tool_name)
    _log.debug("args: %s", args)

    args = _sanitize_args(args)

    try:
        output = await _run_func(entry, args)
    except RuntimeError as exc:
        _log.warning("tool %s failed: %s", tool_name, exc)
        handle = store(tool_name, str(exc), ttl=entry.ttl)
        return ToolOutput(
            handle=handle,
            text=str(exc),
            is_error=True,
        )

    line_count = output.count("\n") + (1 if output and not output.endswith("\n") else 0)
    handle = store(tool_name, output, ttl=entry.ttl)
    _log.info("cached %s -> %s (%d lines)", tool_name, handle, line_count)

    # Apply transforms if requested
    if transforms:
        lines = output.splitlines()
        transformed = apply_transforms(lines, transforms)
        _log.debug(
            "transforms: %d lines -> %d lines",
            len(lines),
            len(transformed),
        )
        text = "\n".join(transformed)
        return ToolOutput(
            handle=handle,
            total_lines=line_count,
            text=text,
        )

    inline = line_count <= INLINE_THRESHOLD
    _log.debug(
        "%s: %d lines, inline=%s",
        tool_name,
        line_count,
        inline,
    )

    return ToolOutput(
        handle=handle,
        total_lines=line_count,
        text=output if inline else None,
        preview=_make_preview(output) if not inline else None,
    )
