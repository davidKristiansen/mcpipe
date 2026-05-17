# mcpipe

> This file is the single source of truth for AI agents working on this codebase.
> It is **stateless** — it describes the current state of the project, not a log of
> changes. Keep it accurate. If you change the architecture, update this file in the
> same commit. If this file contradicts the code, the code wins and this file is stale.

## What is mcpipe

A plugin-based MCP server framework that protects LLM context windows. Any CLI tool
can be exposed as an MCP tool — output is cached and accessed through generic
`paginate` and `search` framework tools instead of dumped into the conversation.

Zero hard dependencies. Python 3.13+.

The name is "MCP" + "pipe" — Unix-style piping for the Model Context Protocol.

## How it works (LLM perspective)

A plugin tool runs, its output is cached to `/tmp/mcpipe/`, and the LLM gets back
a handle + summary. The LLM then uses framework tools to explore the cached output.

```
LLM calls:  git_log(since="1week")
Returns:    { handle: "git_log_1716000000", lines: 847, preview: "..." }

LLM calls:  search(handle="git_log_1716000000", pattern="auth")
Returns:    12 matching lines

LLM calls:  paginate(handle="git_log_1716000000", offset=0, limit=5)
Returns:    first 5 lines
```

One tool produces. Generic tools consume. Plugins never implement search or pagination.

## Architecture

```
┌─────────┐     ┌──────────┐     ┌──────┐
│  Source  │────▶│ Executor │────▶│ Sink │──▶ handle + summary
│stdio/cli│     └──────────┘     └──────┘
└─────────┘          │               │
                ┌────┴────┐     ┌────┴──────────┐
                │ Plugins │     │ /tmp/mcpipe/   │
                │git, ... │     │ <name>_<ts>    │
                └─────────┘     └────────────────┘
                                     ▲
                              ┌──────┴──────┐
                              │  Framework   │
                              │  Tools       │
                              │  - paginate  │
                              │  - search    │
                              └─────────────┘
```

### Two kinds of tools

1. **Plugin tools** — domain-specific (git_log, git_diff, docker_ps). Produce output.
   Registered by plugins. Don't know about caching or pagination.

2. **Framework tools** — generic (paginate, search). Consume cached output via handles.
   Built into mcpipe. Work with any plugin's output.

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
- Each plugin is a module under `mcpipe/plugins/` — the module name is the plugin name
- Plugin name is auto-detected from the module by the `@tool` decorator (no config needed)
- A plugin declares its tools (name, description, arg schema) and how to execute them
- A plugin can be a subprocess wrapper (git, docker, kubectl) or pure Python
- The `list` command groups tools by plugin name
- Plugins provide **sink hints** — advisory preferences for how their output should be delivered

## Sink Hints

Plugins hint at their output characteristics. The framework resolves the actual sink:

1. **User override** — CLI `--output file` always wins
2. **Source default** — MCP defaults to file, CLI to stdout
3. **Plugin hint** — e.g. `git_log` hints file (large), `git_status` hints stdout (small)

Hints are advisory, never mandatory. When output is small enough, the framework may
return it inline regardless of hints.

## Project Layout

```
mcpipe/
  src/mcpipe/
    __init__.py          # Public API: from mcpipe import tool, Cmd, SinkPreference, bootstrap
    __main__.py          # Thin trampoline to cli.main()
    bootstrap.py         # Auto-discover & import all plugins (shared by CLI + MCP server)
    plugin.py            # @tool decorator, Cmd, registry, execute
    cache.py             # File cache (handles, TTL, GC)
    server.py            # MCP stdio JSON-RPC server
    types/               # Type definitions
      __init__.py        # Re-exports for internal use
      protocol.py        # MCP wire types (JSON-RPC, Tool, ToolResult, Init)
      _hints.py          # SinkHint, SinkPreference
    cli/                 # CLI entrypoint
      __init__.py
      args.py            # argv parsing, coercion
      main.py            # Entrypoint logic, wiring
    plugins/             # Built-in plugins (git, docker, ...)
      __init__.py
      git.py
      docker.py
```

## Conventions

- **Zero dependencies** — stdlib only for the core framework. Plugins may declare their own.
- **Async throughout** — the executor and server are async.
- **Errors** — Executor wraps plugin errors into structured `Result` objects with exit code + stderr. Sources translate these into their native error format (JSON-RPC error, CLI exit code).
- **Tests** go in a top-level `tests/` directory, mirroring `src/` structure.

## Current State

CLI works end-to-end: argv parsing, plugin registry, subprocess execution.
`cache.py`, `server.py` are not yet implemented.
