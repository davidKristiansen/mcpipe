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

    command: str  # "run", "list", "server"
    verbosity: int = 0  # 0=warn, 1=info, 2=debug, 3=trace
    color: str = "auto"  # auto|always|never
    config: str | None = None

    # run-specific
    tool: str = ""
    tool_args: dict[str, str] = field(default_factory=dict)

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

    sub = p.add_subparsers(dest="command")

    # -- run --
    run_p = sub.add_parser("run", help="execute a tool")
    run_p.add_argument("tool", help="tool name")

    # -- list --
    sub.add_parser("list", help="list available tools")

    # -- server --
    sub.add_parser("server", help="start MCP stdio server")

    return p


def _parse_tool_args(remainder: list[str]) -> dict[str, str]:
    """Parse leftover --key=value / --flag args meant for the tool."""
    args: dict[str, str] = {}
    for arg in remainder:
        if arg.startswith("--") and "=" in arg:
            key, value = arg[2:].split("=", 1)
            args[key.replace("-", "_")] = value
        elif arg.startswith("--"):
            args[arg[2:].replace("-", "_")] = "true"
    return args


def parse_argv(argv: list[str]) -> Opts:
    """Parse argv into structured Opts."""
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
        opts.tool_args = _parse_tool_args(remainder)
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
