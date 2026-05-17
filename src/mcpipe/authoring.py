"""Authoring tools — CRUD for user plugins and transforms.

These framework tools allow LLMs to create, read, edit, and delete
user-authored plugins and transforms at runtime. Files are written to
$XDG_CONFIG_HOME/mcpipe/{plugins,transforms}/ and picked up by reload.
"""

from __future__ import annotations

import json
from typing import Annotated

from mcpipe.config import (
    ensure_user_dirs,
    user_plugins_dir,
    user_transforms_dir,
)
from mcpipe.log import get_logger
from mcpipe.plugin import tool

_log = get_logger("authoring")

# ---------------------------------------------------------------------------
# Authoring guide — injected into tool descriptions and returned by help tool
# ---------------------------------------------------------------------------

_PLUGIN_GUIDE = """\
# mcpipe Plugin Authoring Guide

## Plugin file
A plugin is a single .py file in the plugins directory.
Each file can register one or more tools via the @tool decorator.
The filename (without .py) becomes the plugin name shown in `list`.

## Imports
```python
from mcpipe import tool, Cmd
from typing import Annotated  # for parameter descriptions
```

## @tool decorator
```python
@tool(
    "Short description of what the tool does",
    read_only=True,     # Does not modify anything (default: False)
    destructive=False,   # Cannot cause irreversible harm (default: True)
    idempotent=True,     # Same args = same result (default: False)
)
def my_tool_name(
    path: Annotated[str, "Description of the path parameter"],
    count: int = 10,
    verbose: bool = False,
) -> Cmd | str:
    ...
```

### Annotation flags
- read_only: True if the tool only reads data, never writes
- destructive: True if the tool can cause irreversible changes (delete, overwrite)
- idempotent: True if calling it twice with the same args has the same effect
- Ask the user if you're unsure about these flags

### Return types
- Return `str` for direct output (Python-computed results)
- Return `Cmd(...)` for subprocess execution:
  ```python
  return Cmd("kubectl", "get", "pods", "-n", namespace)
  ```
  Cmd takes the command and args as positional strings.

### Parameter types
Supported: str, int, float, bool
Use `Annotated[type, "description"]` to add parameter descriptions.
Parameters with defaults are optional; without defaults are required.

## Example: complete plugin
```python
\"\"\"kubectl plugin for mcpipe.\"\"\"
from mcpipe import Cmd, tool
from typing import Annotated

@tool("List Kubernetes pods", read_only=True, idempotent=True)
def kubectl_get_pods(
    namespace: Annotated[str, "Kubernetes namespace"] = "default",
    all_namespaces: bool = False,
) -> Cmd:
    args = ["kubectl", "get", "pods"]
    if all_namespaces:
        args.append("--all-namespaces")
    else:
        args.extend(["-n", namespace])
    return Cmd(*args)

@tool("Delete a Kubernetes pod", destructive=True)
def kubectl_delete_pod(
    name: Annotated[str, "Pod name"],
    namespace: Annotated[str, "Namespace"] = "default",
) -> Cmd:
    return Cmd("kubectl", "delete", "pod", name, "-n", namespace)
```
"""

_TRANSFORM_GUIDE = """\
# mcpipe Transform Authoring Guide

## Transform file
A transform is a single .py file in the transforms directory.
Each file can register one or more transforms via the @transform decorator.

## Imports
```python
from mcpipe import transform
from typing import Annotated  # for parameter descriptions
```

## @transform decorator
```python
@transform("Short description of what the transform does")
def my_transform(
    lines: list[str],
    param: Annotated[str, "Description"],
) -> list[str]:
    # lines in -> lines out, pure function
    return [line for line in lines if some_condition(line)]
```

### Rules
- First parameter MUST be `lines: list[str]`
- MUST return `list[str]`
- Must be a pure function — no side effects, no cache mutation
- Additional parameters become transform-specific options
- The function name becomes the transform name

## Example: complete transform
```python
\"\"\"Custom transforms for sorting and deduplication.\"\"\"
from mcpipe import transform
from typing import Annotated

@transform("Sort lines alphabetically")
def sort(lines: list[str], reverse: bool = False) -> list[str]:
    return sorted(lines, reverse=reverse)

@transform("Remove duplicate lines preserving order")
def dedup(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for line in lines:
        if line not in seen:
            seen.add(line)
            result.append(line)
    return result

@transform("Keep only lines containing a JSON object")
def json_only(lines: list[str]) -> list[str]:
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            result.append(line)
    return result
```
"""

# ---------------------------------------------------------------------------
# Help tool
# ---------------------------------------------------------------------------


@tool(
    "Get the mcpipe authoring guide for writing plugins or transforms. "
    "Call this BEFORE creating or editing plugins/transforms.",
    read_only=True,
    destructive=False,
    idempotent=True,
)
def authoring_help(
    topic: Annotated[
        str, "Topic: 'plugin', 'transform', or 'both'"
    ] = "both",
) -> str:
    if topic == "plugin":
        return _PLUGIN_GUIDE
    if topic == "transform":
        return _TRANSFORM_GUIDE
    return _PLUGIN_GUIDE + "\n---\n\n" + _TRANSFORM_GUIDE


# ---------------------------------------------------------------------------
# List user extensions
# ---------------------------------------------------------------------------


@tool(
    "List user-authored plugins and transforms in the config directory",
    read_only=True,
    destructive=False,
    idempotent=True,
)
def list_user_extensions() -> str:
    plugins_dir = user_plugins_dir()
    transforms_dir = user_transforms_dir()

    result: dict[str, list[str] | str] = {"plugins": [], "transforms": []}

    if plugins_dir.is_dir():
        for f in sorted(plugins_dir.glob("*.py")):
            if not f.name.startswith("_"):
                result.setdefault("plugins", [])
                plugins = result["plugins"]
                assert isinstance(plugins, list)
                plugins.append(f.name)

    if transforms_dir.is_dir():
        for f in sorted(transforms_dir.glob("*.py")):
            if not f.name.startswith("_"):
                result.setdefault("transforms", [])
                transforms = result["transforms"]
                assert isinstance(transforms, list)
                transforms.append(f.name)

    result["plugins_dir"] = str(plugins_dir)
    result["transforms_dir"] = str(transforms_dir)

    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


@tool(
    "Read the source code of a user plugin or transform file",
    read_only=True,
    destructive=False,
    idempotent=True,
)
def read_extension(
    name: Annotated[str, "Filename without .py (e.g. 'kubectl')"],
    kind: Annotated[str, "'plugin' or 'transform'"] = "plugin",
) -> str:
    directory = user_plugins_dir() if kind == "plugin" else user_transforms_dir()
    path = directory / f"{name}.py"

    if not path.exists():
        return f"Error: {kind} '{name}' not found at {path}"

    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Create / Edit (same operation — write file, then reload)
# ---------------------------------------------------------------------------


@tool(
    "Create or overwrite a user plugin file. "
    "The content must be valid Python with @tool-decorated functions. "
    "Call `authoring_help(topic='plugin')` first for the API reference. "
    "Call `reload` after to register the new tools.",
    read_only=False,
    destructive=False,
    idempotent=True,
)
def write_plugin(
    name: Annotated[str, "Filename without .py (e.g. 'kubectl')"],
    content: Annotated[str, "Complete Python source code for the plugin"],
) -> str:
    ensure_user_dirs()
    path = user_plugins_dir() / f"{name}.py"
    existed = path.exists()
    path.write_text(content, encoding="utf-8")

    action = "updated" if existed else "created"
    return (
        f"Plugin '{name}' {action} at {path}\n"
        f"Call `reload` to register the new tools."
    )


@tool(
    "Create or overwrite a user transform file. "
    "The content must be valid Python with @transform-decorated functions. "
    "Call `authoring_help(topic='transform')` first for the API reference. "
    "Call `reload` after to register the new transforms.",
    read_only=False,
    destructive=False,
    idempotent=True,
)
def write_transform(
    name: Annotated[str, "Filename without .py (e.g. 'sort')"],
    content: Annotated[str, "Complete Python source code for the transform"],
) -> str:
    ensure_user_dirs()
    path = user_transforms_dir() / f"{name}.py"
    existed = path.exists()
    path.write_text(content, encoding="utf-8")

    action = "updated" if existed else "created"
    return (
        f"Transform '{name}' {action} at {path}\n"
        f"Call `reload` to register the new transforms."
    )


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@tool(
    "Delete a user plugin file. This removes the file permanently. "
    "Call `reload` after to unregister the tools.",
    read_only=False,
    destructive=True,
    idempotent=True,
)
def delete_plugin(
    name: Annotated[str, "Filename without .py (e.g. 'kubectl')"],
) -> str:
    path = user_plugins_dir() / f"{name}.py"
    if not path.exists():
        return f"Error: plugin '{name}' not found at {path}"
    path.unlink()
    return (
        f"Plugin '{name}' deleted from {path}\n"
        f"Call `reload` to unregister its tools."
    )


@tool(
    "Delete a user transform file. This removes the file permanently. "
    "Call `reload` after to unregister the transforms.",
    read_only=False,
    destructive=True,
    idempotent=True,
)
def delete_transform(
    name: Annotated[str, "Filename without .py (e.g. 'sort')"],
) -> str:
    path = user_transforms_dir() / f"{name}.py"
    if not path.exists():
        return f"Error: transform '{name}' not found at {path}"
    path.unlink()
    return (
        f"Transform '{name}' deleted from {path}\n"
        f"Call `reload` to unregister its transforms."
    )
