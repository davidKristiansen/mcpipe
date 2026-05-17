"""Logging setup for mcpipe.

All output goes to stderr so stdout stays clean for MCP JSON-RPC.
Verbosity 0 = silent (WARNING only, effectively nothing in normal use).
"""

from __future__ import annotations

import logging
import sys


class _Ansi:
    GREY = "\033[90m"
    BLUE = "\033[94m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD_RED = "\033[1;91m"
    RESET = "\033[0m"


class _DeltaFormatter(logging.Formatter):
    """Compact formatter: delta timestamp + colored message to stderr."""

    _first: float | None = None

    def __init__(self, use_color: bool = True) -> None:
        super().__init__(datefmt="%H:%M:%S")
        self._color = use_color

    def _prefix(self, record: logging.LogRecord) -> str:
        if _DeltaFormatter._first is None:
            _DeltaFormatter._first = record.created
            ts = self.formatTime(record, self.datefmt)
            if self._color:
                return f"{_Ansi.GREY}{ts}{_Ansi.RESET}"
            return ts

        delta = record.created - _DeltaFormatter._first
        m, s = divmod(int(delta), 60)
        h, m = divmod(m, 60)
        tag = f"+{h:02d}:{m:02d}:{s:02d}"
        if self._color:
            return f"{_Ansi.GREY}{tag}{_Ansi.RESET}"
        return tag

    def _level_color(self, levelno: int) -> str:
        if not self._color:
            return ""
        if levelno >= logging.ERROR:
            return _Ansi.RED
        if levelno >= logging.WARNING:
            return _Ansi.YELLOW
        if levelno >= logging.DEBUG:
            return ""
        return _Ansi.BLUE  # TRACE

    def format(self, record: logging.LogRecord) -> str:
        prefix = self._prefix(record)
        color = self._level_color(record.levelno)
        reset = _Ansi.RESET if self._color and color else ""
        return f"{prefix} {color}{record.getMessage()}{reset}"


# Trace level (below DEBUG)
TRACE = 5
logging.addLevelName(TRACE, "TRACE")

_VERBOSITY_MAP: dict[int, int] = {
    0: logging.WARNING,
    1: logging.INFO,
    2: logging.DEBUG,
}


def setup_logging(
    verbosity: int = 0,
    color: bool = True,
) -> None:
    """Configure the mcpipe logger. Must be called once at startup."""
    level = _VERBOSITY_MAP.get(verbosity, TRACE)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_DeltaFormatter(use_color=color))

    root = logging.getLogger("mcpipe")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """Get a child logger under the mcpipe namespace."""
    return logging.getLogger(f"mcpipe.{name}")
