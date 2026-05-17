"""Git plugin for mcpipe."""

from __future__ import annotations

from typing import Annotated

from mcpipe import Cmd, SinkPreference, tool


@tool(
    "Show commit log",
    read_only=True,
    destructive=False,
    idempotent=True,
    sink=SinkPreference.FILE,
)
def git_log(
    repo_path: Annotated[str, "Path to the git repository"] = ".",
    max_count: Annotated[int, "Number of commits to show"] = 10,
    since: Annotated[str, "Show commits after this date (e.g. '1 week ago')"] = "",
    path: Annotated[str, "Limit to commits touching this path"] = "",
) -> Cmd:
    args = ["git", "-C", repo_path, "log", f"--max-count={max_count}"]
    if since:
        args.extend(["--since", since])
    if path:
        args.extend(["--", path])
    return Cmd(*args)
