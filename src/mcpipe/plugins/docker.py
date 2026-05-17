"""Docker plugin for mcpipe."""

from __future__ import annotations

from typing import Annotated

from mcpipe import Cmd, SinkPreference, tool


@tool(
    "List running containers",
    read_only=True,
    destructive=False,
    idempotent=True,
    sink=SinkPreference.STREAM,
)
def docker_ps(
    all: Annotated[bool, "Show all containers (including stopped)"] = False,
    format: Annotated[str, "Go template for output format"] = "",
) -> Cmd:
    args = ["docker", "ps"]
    if all:
        args.append("--all")
    if format:
        args.extend(["--format", format])
    return Cmd(*args)


@tool(
    "Show container logs",
    read_only=True,
    destructive=False,
    idempotent=True,
    sink=SinkPreference.FILE,
)
def docker_logs(
    container: Annotated[str, "Container name or ID"],
    tail: Annotated[int, "Number of lines from the end"] = 100,
    since: Annotated[str, "Show logs since timestamp (e.g. '1h', '2024-01-01')"] = "",
) -> Cmd:
    args = ["docker", "logs", f"--tail={tail}"]
    if since:
        args.extend(["--since", since])
    args.append(container)
    return Cmd(*args)


@tool(
    "List Docker images",
    read_only=True,
    destructive=False,
    idempotent=True,
    sink=SinkPreference.STREAM,
)
def docker_images(
    filter: Annotated[str, "Filter by reference (e.g. 'nginx')"] = "",
) -> Cmd:
    args = ["docker", "images"]
    if filter:
        args.append(filter)
    return Cmd(*args)
