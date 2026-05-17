# mcpipe

> This file is the single source of truth for AI agents working on this codebase.
> It is **stateless** — it describes the current state of the project, not a log of
> changes. Keep it accurate. If you change the architecture, update this file in the
> same commit. If this file contradicts the code, the code wins and this file is stale.

## What is mcpipe

A plugin-based MCP server framework that protects LLM context windows. Any CLI tool
can be exposed as an MCP tool — output is cached and accessed through generic
`view` framework tool instead of dumped into the conversation.
Output can be post-processed through a pluggable **transform** pipeline.

Zero hard dependencies. Python 3.12+.

The name is "MCP" + "pipe" — Unix-style piping for the Model Context Protocol.

## How it works (LLM perspective)

A plugin tool runs, its output is cached to `/tmp/mcpipe/`, and the LLM gets back
a handle + summary. The LLM then uses framework tools to explore the cached output.

```
LLM calls:  git_log(since="1week")
Returns:    { handle: "git_log_1716000000", lines: 847, preview: "..." }

LLM calls:  view(handle="git_log_1716000000", _search="auth")
Returns:    matching lines

LLM calls:  view(handle="git_log_1716000000", _offset=0, _limit=5)
Returns:    first 5 lines
```

One tool produces. Generic tools consume. Plugins never implement search or pagination.

## Architecture

```
┌─────────┐     ┌──────────┐     ┌──────┐     ┌────────────┐
│  Source  │────▶│ Executor │────▶│ Sink │────▶│ Transforms │──▶ result
│stdio/cli│     └──────────┘     └──────┘     └────────────┘
└─────────┘          │               │              │
                ┌────┴────┐     ┌────┴──────────┐   │ lines in → lines out
                │ Plugins │     │ /tmp/mcpipe/   │   │ pure, composable
                │git, ... │     │ <name>_<ts>    │   │ cache never mutated
                └─────────┘     └────────────────┘   │
                                     ▲          ┌────┴────────┐
                              ┌──────┴──────┐   │ @transform   │
                              │  Framework   │   │ search,limit │
                              │  Tools       │   │ offset,head  │
                              │  - view      │   │ tail, ...    │
                              │  - search    │   │ (extensible) │
                              └─────────────┘   └─────────────┘
```

### Two kinds of tools

1. **Plugin tools** — domain-specific (git_log, git_diff, docker_ps). Produce output.
   Registered by plugins. Don't know about caching or pagination.

2. **Framework tools** — generic (view, handles, reload, authoring). Consume cached output
   or manage mcpipe itself. Built into mcpipe. Work with any plugin's output.
   `view` loads cached output by handle — meta-params do the filtering.
   `reload` hot-reloads plugins and transforms from disk without restarting.
   Authoring tools (write/read/delete plugin/transform) manage user extensions.

### Transforms — pluggable post-processing

Transforms are pure functions: `lines in → lines out`. They run after caching and
never mutate the cache. Registered via `@transform` decorator.

**Built-in transforms** (registered as `weak=True` — user overrides replace them):
- `search` — filter lines by regex pattern
- `limit` — return at most N lines
- `offset` — skip first N lines
- `head` — first N lines
- `tail` — last N lines

**Custom transforms**: any plugin can register new transforms:
```python
from mcpipe import transform

@transform("Sort lines alphabetically")
def sort(lines: list[str], reverse: bool = False) -> list[str]:
    return sorted(lines, reverse=reverse)
```

**Override builtins**: register a transform with the same name — it fully replaces
the builtin. For example, a plugin could replace `search` with a native implementation.

**output_filter — per-tool defaults**: tools can declare default transforms via
`output_filter=[TransformStep("head", {"n": 10})]` on the `@tool` decorator.
These run automatically when the caller sends no `_meta` transform params.
Caller-provided transforms replace defaults entirely (no merging).

### Entrypoints

Two ways in — both share the plugin registry and cache:

- **CLI** (`cli/`) — parse argv, run tool, print output. For humans and scripts.
- **MCP server** (`server.py`) — JSON-RPC over stdio. For LLM clients.

### Cache

Output caching lives in `cache.py`. Writes to `/tmp/mcpipe/`, manages handles and TTL.

### Cache

- Location: `/tmp/mcpipe/`
- Handle format: `<tool_name>_<unix_timestamp>` (e.g. `git_log_1716000000`)
- Handles are descriptive — you can tell what produced it and when at a glance
- TTL-based garbage collection cleans up old entries

### Plugins — domain logic
- Each plugin is a module under `mcpipe/plugins/` (built-in) or
  `$XDG_CONFIG_HOME/mcpipe/plugins/` (user-authored)
- Plugin name is auto-detected from the module by the `@tool` decorator (no config needed)
- A plugin declares its tools (name, description, arg schema) and how to execute them
- A plugin can be a subprocess wrapper (git, docker, kubectl) or pure Python
- The `list` command groups tools by plugin name

### User extensions

User plugins and transforms live in `$XDG_CONFIG_HOME/mcpipe/` (default `~/.config/mcpipe/`):
- `plugins/*.py` — user-authored plugin files
- `transforms/*.py` — user-authored transform files

These are auto-discovered by `bootstrap()` after built-in modules.
LLMs can create/edit/delete them via authoring framework tools:
- `authoring_help` — returns the full plugin/transform API guide
- `list_user_extensions` — lists files in the user config dirs
- `read_extension` — reads a user plugin/transform source file
- `write_plugin` / `write_transform` — creates or overwrites a file
- `delete_plugin` / `delete_transform` — removes a file
- `reload` — hot-reloads all modules to pick up changes

## Project Layout

```
mcpipe/
  src/mcpipe/
    __init__.py          # Public API: from mcpipe import tool, Cmd, bootstrap
    __main__.py          # Entrypoints: cli() and mcp() for console_scripts
    bootstrap.py         # Auto-discover & import all plugins (shared by CLI + MCP server)
    plugin.py            # @tool decorator, Cmd, ToolOutput, execute, registry
    transform.py         # @transform decorator, TransformStep, apply_transforms, builtins
    cache.py             # File cache (handles, TTL, GC, CachedOutput with slice/search)
    server.py            # MCP stdio JSON-RPC server (initialize, tools/list, tools/call)
    framework.py         # Framework tools: view, handles, reload
    log.py               # Delta-timestamp colored logging to stderr
    _version.py          # Version/appname from importlib.metadata
    types/               # Type definitions
      __init__.py        # Re-exports for internal use
      protocol.py        # MCP wire types (JSON-RPC, Tool, ToolResult, Init)
      _hints.py          # (reserved for future hints)
    cli/                 # CLI entrypoint
      __init__.py
      args.py            # argv parsing, coercion
      main.py            # Entrypoint logic, wiring
    plugins/             # Built-in plugins (git, docker, ...)
      __init__.py
      git.py
      docker.py
```

## CLI Usage

```
mcpipe [global flags] run [-T NAME key=val ...] <tool> [tool args...]
mcpipe [global flags] view <handle> [-T NAME key=val ...]
mcpipe list
mcpipe server
```

- Transform flags: `--transform NAME key=value` or `-T NAME key=value` (repeatable, order matters)
- Tool args: bare `key=value` after `--` separator
- `--` is optional but recommended for clarity

## MCP Server

The MCP server (`server.py`) speaks JSON-RPC 2.0 over stdio (newline-delimited).

Supported methods:
- `initialize` → capabilities + server info
- `notifications/initialized` → no-op
- `tools/list` → all registered tools with schemas + annotations
- `tools/call` → execute tool, return ToolResult
- `ping` → pong

### Pipeline meta-params

Any tool call can include pipeline meta-params prefixed with `_`:
- `_offset` (int) — start at this line
- `_limit` (int) — max lines to return
- `_search` (str) — filter output by regex

These are extracted before dispatch and desugared into transform steps.
Plugins never see them.

### Arg sanitization

`execute()` runs `os.path.expanduser` + `os.path.expandvars` on all string args
before passing to the plugin. Both CLI and MCP benefit from this.

## Conventions

- **Zero dependencies** — stdlib only for the core framework. Plugins may declare their own.
- **Async throughout** — the executor and server are async.
- **Errors** — Executor wraps plugin errors into structured `Result` objects with exit code + stderr. Sources translate these into their native error format (JSON-RPC error, CLI exit code).
- **Tests** go in a top-level `tests/` directory, mirroring `src/` structure.

## Current State

CLI and MCP server both work end-to-end. Plugin registry, cache pipeline,
framework tools (view/handles/reload), arg sanitization all functional.
Server registered in opencode config for LLM testing.
