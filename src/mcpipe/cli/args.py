"""CLI argument parsing for mcpipe.

Uses argparse with subcommands. Tool args (--key=value) are passed through
via parse_known_args so argparse doesn't reject them.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Opts:
    """Parsed CLI options."""

    command: str  # "run", "list", "view", "server"
    verbosity: int = 0  # 0=warn, 1=info, 2=debug, 3=trace
    color: str = "auto"  # auto|always|never
    config: str | None = None

    # run/view-specific
    tool: str = ""
    tool_args: dict[str, str] = field(default_factory=dict)

    # transform steps (run and view subcommands)
    transforms: list[tuple[str, dict[str, str]]] = field(default_factory=list)

    # view subcommand
    handle: str = ""

    # list subcommand
    filter: str | None = None
    plugin_filter: str | None = None
    tools_only: bool = False
    transforms_only: bool = False

    # server subcommand
    transport: str = "stdio"

    @property
    def use_color(self) -> bool:
        if self.color == "always":
            return True
        if self.color == "never":
            return False
        return sys.stdout.isatty()


def build_parser() -> argparse.ArgumentParser:
    from mcpipe._version import __appname__, __version__

    p = argparse.ArgumentParser(
        prog=__appname__,
        description="Plugin-based MCP server framework.",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"{__appname__} {__version__}",
    )
    p.add_argument(
        "-v",
        action="count",
        default=0,
        dest="verbosity",
        help="increase verbosity (-v info, -vv debug, -vvv trace)",
    )
    p.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="colorize output (default: auto)",
    )
    p.add_argument("--config", metavar="PATH", help="config file path")

    _transform_epilog = (
        "transforms:\n"
        "  -T NAME key=val    apply a transform (repeatable, order matters)\n"
        "  -T NAME=val        shorthand for single-param transforms\n"
        "\n"
        "examples:\n"
        "  -T search pattern=auth    filter lines matching 'auth'\n"
        "  -T head=10                first 10 lines\n"
        "  -T offset=5 -T limit=20   lines 5-24\n"
    )

    sub = p.add_subparsers(dest="command")

    # -- run --
    run_p = sub.add_parser(
        "run",
        help="execute a tool",
        usage="%(prog)s [-T NAME key=v ...] <tool> [tool args...]",
        epilog=_transform_epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    run_p.add_argument("tool", help="tool name")
    run_p.add_argument(
        "tool_remainder", nargs=argparse.REMAINDER,
        help=argparse.SUPPRESS,
    )

    # -- list --
    list_p = sub.add_parser("list", help="list available tools and transforms")
    list_p.add_argument(
        "filter", nargs="?", default=None,
        help="substring filter on tool/transform names",
    )
    list_p.add_argument(
        "-p", "--plugin", default=None,
        help="show only tools from this plugin",
    )
    list_p.add_argument(
        "--tools-only", action="store_true",
        help="show only tools (hide transforms)",
    )
    list_p.add_argument(
        "--transforms-only", action="store_true",
        help="show only transforms (hide tools)",
    )

    # -- view --
    view_p = sub.add_parser(
        "view",
        help="view cached output by handle (with optional transforms)",
        usage="%(prog)s <handle> [-T NAME key=v ...]",
        epilog=_transform_epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    view_p.add_argument("handle", help="cache handle from a previous run")

    # -- server --
    srv_p = sub.add_parser("server", help="start MCP server")
    srv_p.add_argument(
        "--transport",
        choices=("stdio",),
        default="stdio",
        help="transport protocol (default: stdio)",
    )

    return p


def _parse_tool_args(remainder: list[str]) -> dict[str, str]:
    """Parse tool args in key=value or --key=value format."""
    args: dict[str, str] = {}
    for arg in remainder:
        if arg == "--":
            continue
        if arg.startswith("--") and "=" in arg:
            key, value = arg[2:].split("=", 1)
            args[key.replace("-", "_")] = value
        elif arg.startswith("--"):
            args[arg[2:].replace("-", "_")] = "true"
        elif "=" in arg:
            key, value = arg.split("=", 1)
            args[key.replace("-", "_")] = value
    return args


def _extract_transforms(
    argv: list[str],
) -> tuple[list[str], list[tuple[str, dict[str, str]]]]:
    """Pre-parse --transform / -T blocks from argv before argparse.

    Each --transform consumes: NAME [key=value ...] until the next flag or --.
    Returns (remaining_argv, transforms).

    Examples:
        --transform search pattern=text --transform limit n=10
        -T head n=5
        --transform limit n=10
    """
    remaining: list[str] = []
    transforms: list[tuple[str, dict[str, str]]] = []
    i = 0

    while i < len(argv):
        arg = argv[i]
        if arg in ("--transform", "-T"):
            i += 1
            if i >= len(argv):
                break
            # Next token is the transform name (or name=value shorthand)
            name_tok = argv[i]
            i += 1
            if "=" in name_tok:
                name, positional = name_tok.split("=", 1)
                params: dict[str, str] = {"_positional": positional}
            else:
                name = name_tok
                params = {}
            while i < len(argv):
                tok = argv[i]
                if tok.startswith("-") or tok == "--" or "=" not in tok:
                    break
                k, v = tok.split("=", 1)
                params[k] = v
                i += 1
            transforms.append((name, params))
        else:
            remaining.append(arg)
            i += 1

    return remaining, transforms


def parse_argv(argv: list[str]) -> Opts:
    """Parse argv into structured Opts."""
    # Extract --transform blocks before argparse
    # (argparse can't handle multi-value repeatable flags)
    argv, transforms = _extract_transforms(argv)

    parser = build_parser()
    ns, remainder = parser.parse_known_args(argv)

    if ns.command is None:
        parser.print_help()
        raise SystemExit(1)

    opts = Opts(
        command=ns.command,
        verbosity=ns.verbosity,
        color=ns.color,
        config=ns.config,
    )

    if ns.command == "run":
        opts.tool = ns.tool
        opts.tool_args = _parse_tool_args(
            ns.tool_remainder + remainder,
        )
        opts.transforms = transforms
    elif ns.command == "view":
        opts.handle = ns.handle
        opts.transforms = transforms
    elif ns.command == "list":
        opts.filter = ns.filter
        opts.plugin_filter = ns.plugin
        opts.tools_only = ns.tools_only
        opts.transforms_only = ns.transforms_only
    elif ns.command == "server":
        opts.transport = ns.transport
    elif remainder:
        parser.error(f"unrecognized arguments: {' '.join(remainder)}")

    return opts


def coerce_args(
    tool_name: str,
    raw: dict[str, str],
    schema: dict[str, Any],
) -> dict[str, str | int | float | bool]:
    """Coerce string args to types based on tool JSON schema."""
    props = schema.get("properties", {})
    coerced: dict[str, str | int | float | bool] = {}

    for key, value in raw.items():
        schema_type = props.get(key, {}).get("type", "string")
        match schema_type:
            case "integer":
                coerced[key] = int(value)
            case "number":
                coerced[key] = float(value)
            case "boolean":
                coerced[key] = value.lower() in ("true", "1", "yes")
            case _:
                coerced[key] = value

    return coerced
