"""CLI entrypoint for mcpipe."""

from __future__ import annotations

import sys

from mcpipe._version import __appname__, __version__
from mcpipe.bootstrap import bootstrap
from mcpipe.cli.args import Opts, coerce_args, parse_argv
from mcpipe.log import get_logger, setup_logging
from mcpipe.plugin import execute, get_tools
from mcpipe.transform import TransformStep, apply_transforms

_log = get_logger("cli")


async def _run(opts: Opts) -> int:
    entry = get_tools().get(opts.tool)
    if entry is None:
        print(f"Error: unknown tool '{opts.tool}'", file=sys.stderr)
        return 1

    args = coerce_args(opts.tool, opts.tool_args, entry.tool.input_schema)
    _log.debug("tool=%s args=%s", opts.tool, args)

    transforms: list[TransformStep] | None = None
    if opts.transforms:
        transforms = [
            TransformStep(name=name, params=params)
            for name, params in opts.transforms
        ]
        _log.debug("transforms: %s", transforms)

    try:
        result = await execute(opts.tool, args, transforms=transforms)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if result.is_error:
        print(result.text, file=sys.stderr)
        return 1

    if result.is_inline:
        print(result.text, end="")
    else:
        print(f"handle:  {result.handle}")
        print(f"lines:   {result.total_lines}")
        print(f"preview:\n{result.preview}")

    _log.debug("handle: %s", result.handle)
    return 0


async def _view(opts: Opts) -> int:
    """View cached output by handle, with optional transforms."""
    from mcpipe.cache import load

    try:
        cached = load(opts.handle)
    except FileNotFoundError:
        print(
            f"Error: no cached output for handle '{opts.handle}'",
            file=sys.stderr,
        )
        return 1

    lines = cached.lines

    if opts.transforms:
        steps = [
            TransformStep(name=name, params=params)
            for name, params in opts.transforms
        ]
        _log.debug("transforms: %s", steps)
        try:
            lines = apply_transforms(lines, steps)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    if lines:
        print("\n".join(lines), end="")
    return 0


async def _list(opts: Opts) -> int:
    filt = opts.filter
    show_tools = not opts.transforms_only
    show_transforms = not opts.tools_only

    if show_tools:
        tools = get_tools()
        # Group by plugin
        by_plugin: dict[str, list[tuple[str, str]]] = {}
        for name, entry in sorted(tools.items()):
            plugin = entry.plugin
            if opts.plugin_filter and plugin != opts.plugin_filter:
                continue
            if filt and filt not in name:
                continue
            desc = entry.tool.description
            by_plugin.setdefault(plugin, []).append((name, desc))

        if by_plugin:
            print("\n  Tools")
            for plugin, entries in sorted(by_plugin.items()):
                print(f"\n    [{plugin}]")
                for name, desc in entries:
                    print(f"      {name:20s} {desc}")
        elif not show_transforms:
            print("No matching tools.")

    if show_transforms:
        from mcpipe.transform import get_transforms

        transforms = get_transforms()
        filtered = {
            n: e for n, e in transforms.items()
            if not filt or filt in n
        }
        if filtered:
            print("\n  Transforms\n")
            for name, entry in sorted(filtered.items()):
                weak = " (builtin)" if entry.weak else ""
                print(f"    {name:20s} {entry.description}{weak}")

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
        case "view":
            return await _view(opts)
        case "list":
            return await _list(opts)
        case "server":
            from mcpipe.server import serve

            await serve(transport=opts.transport)
            return 0
        case _:
            return 1
