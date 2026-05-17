"""CLI entrypoint for mcpipe."""

from __future__ import annotations

import sys

from mcpipe._version import __appname__, __version__
from mcpipe.bootstrap import bootstrap
from mcpipe.cli.args import Opts, coerce_args, parse_argv
from mcpipe.log import get_logger, setup_logging
from mcpipe.plugin import execute, get_tools

_log = get_logger("cli")


async def _run(opts: Opts) -> int:
    entry = get_tools().get(opts.tool)
    if entry is None:
        print(f"Error: unknown tool '{opts.tool}'", file=sys.stderr)
        return 1

    args = coerce_args(opts.tool, opts.tool_args, entry.tool.input_schema)
    _log.debug("tool=%s args=%s", opts.tool, args)

    try:
        result = await execute(opts.tool, args)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if result.is_error:
        print(result.text, file=sys.stderr)
        return 1

    if result.is_cached:
        print(f"handle:  {result.handle}")
        print(f"lines:   {result.total_lines}")
        print(f"preview:\n{result.preview}")
    else:
        print(result.text or "", end="")
    return 0


async def _list() -> int:
    tools = get_tools()
    if not tools:
        print("No tools registered.")
        return 0

    # Group by plugin
    by_plugin: dict[str, list[tuple[str, str]]] = {}
    for name, entry in sorted(tools.items()):
        by_plugin.setdefault(entry.plugin, []).append((name, entry.tool.description))

    for plugin, entries in sorted(by_plugin.items()):
        print(f"\n  {plugin}")
        for name, desc in entries:
            print(f"    {name:20s} {desc}")
    print()
    return 0


async def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    try:
        opts = parse_argv(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1

    setup_logging(opts.verbosity, color=opts.use_color)
    _log.info("%s %s", __appname__, __version__)
    _log.debug("command=%s verbosity=%d", opts.command, opts.verbosity)

    bootstrap()

    match opts.command:
        case "run":
            return await _run(opts)
        case "list":
            return await _list()
        case "server":
            print("MCP server not yet implemented.", file=sys.stderr)
            return 1
        case _:
            return 1
