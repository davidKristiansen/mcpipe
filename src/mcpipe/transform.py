"""Transform pipeline for mcpipe.

Transforms are composable, pure functions: lines in, lines out.
They operate on tool output *after* caching — they never mutate the cache.

Built-in transforms (search, limit, offset) are registered as weak entries.
Any user @transform with the same name replaces the builtin.
"""

from __future__ import annotations

import inspect
import typing
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, get_type_hints

from mcpipe.log import get_logger

_log = get_logger("transform")


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class TransformStep:
    """A single transform invocation: name + params."""

    name: str
    params: dict[str, Any]


@dataclass(slots=True)
class _TransformEntry:
    func: Callable[..., list[str]]
    description: str
    param_schema: dict[str, Any]
    weak: bool  # builtins are weak — user registrations replace them


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, _TransformEntry] = {}


def get_transforms() -> dict[str, _TransformEntry]:
    return _REGISTRY


def _clear_transforms() -> set[str]:
    """Remove all registered transforms. Returns removed names."""
    removed = set(_REGISTRY.keys())
    _REGISTRY.clear()
    return removed


_PY_TO_JSON: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def _build_param_schema(func: Callable) -> dict[str, Any]:
    """Build JSON schema for transform params (excludes 'lines' arg)."""
    hints = get_type_hints(func, include_extras=True)
    sig = inspect.signature(func)
    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, param in sig.parameters.items():
        if name == "lines":
            continue
        hint = hints.get(name, str)
        description = None

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


def transform(description: str, *, weak: bool = False) -> Callable:
    """Register a function as a transform.

    The function must accept `lines: list[str]` as its first arg
    and return `list[str]`. Additional params are transform-specific.

    weak=True marks builtins — user registrations with the same name
    replace them silently.
    """

    def decorator[F: Callable[..., list[str]]](func: F) -> F:
        name: str = getattr(func, "__name__")  # noqa: B009
        existing = _REGISTRY.get(name)

        # Don't let a weak entry overwrite a strong one
        if existing and not existing.weak and weak:
            _log.debug("weak transform %r skipped — strong override exists", name)
            return func

        entry = _TransformEntry(
            func=func,
            description=description,
            param_schema=_build_param_schema(func),
            weak=weak,
        )
        _REGISTRY[name] = entry
        if existing and not weak:
            _log.info("transform %r overridden by user registration", name)
        else:
            _log.debug("registered transform %r (weak=%s)", name, weak)
        return func

    return decorator


# ---------------------------------------------------------------------------
# Apply transforms
# ---------------------------------------------------------------------------


def apply_transforms(
    lines: list[str],
    steps: list[TransformStep],
) -> list[str]:
    """Run a chain of transforms on lines. Pure — no side effects."""
    for step in steps:
        entry = _REGISTRY.get(step.name)
        if entry is None:
            available = list(_REGISTRY.keys())
            raise ValueError(
                f"Unknown transform: '{step.name}'. "
                f"Available: {', '.join(available) or '(none)'}",
            )

        params = _resolve_positional(step.params, entry)
        _log.debug("applying transform %r params=%s", step.name, params)
        try:
            lines = entry.func(lines, **params)
        except TypeError as exc:
            known = list(entry.param_schema.get("properties", {}).keys())
            available = list(_REGISTRY.keys())
            raise ValueError(
                f"Transform '{step.name}': {exc}. "
                f"Known params: {', '.join(known) or '(none)'}. "
                f"Available transforms: {', '.join(available)}",
            ) from None
    return lines


def _resolve_positional(
    params: dict[str, Any],
    entry: _TransformEntry,
) -> dict[str, Any]:
    """Resolve _positional shorthand and coerce string params to correct types."""
    resolved = dict(params)
    schema_props = entry.param_schema.get("properties", {})
    required = entry.param_schema.get("required", [])

    # Resolve positional shorthand
    if "_positional" in resolved:
        value = resolved.pop("_positional")
        target = required[0] if required else next(iter(schema_props), None)
        if target:
            resolved[target] = value

    # Coerce string values to schema types
    for key, value in resolved.items():
        if not isinstance(value, str):
            continue
        prop_type = schema_props.get(key, {}).get("type", "string")
        if prop_type == "integer":
            resolved[key] = int(value)
        elif prop_type == "number":
            resolved[key] = float(value)
        elif prop_type == "boolean":
            resolved[key] = value.lower() in ("true", "1", "yes")

    return resolved
