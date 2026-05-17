"""CLI entrypoint for mcpipe."""

import asyncio
import sys

from mcpipe.cli import main


def cli() -> None:
    sys.exit(asyncio.run(main()))

if __name__ == "__main__":
    cli()
