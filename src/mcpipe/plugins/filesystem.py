"""Filesystem plugin for mcpipe.

Read/write files, create/list/delete directories, move files,
search files, and get file metadata.

Access is restricted to allowed roots (configurable). By default,
only the current working directory tree is allowed.
"""

from __future__ import annotations

import os
import stat
import time
from pathlib import Path
from typing import Annotated

from mcpipe import Cmd, tool

# ---------------------------------------------------------------------------
# Roots — allowed directory trees.  Set FS_ROOTS env var to a colon-separated
# list of absolute paths, or leave empty to allow only CWD.
# ---------------------------------------------------------------------------

_roots: list[Path] | None = None


def _get_roots() -> list[Path]:
    """Return allowed root directories (resolved, cached)."""
    global _roots
    if _roots is None:
        env = os.environ.get("FS_ROOTS", "")
        if env:
            _roots = [Path(p).resolve() for p in env.split(":") if p]
        else:
            _roots = [Path.cwd().resolve()]
    return _roots


def _resolve(path: str) -> Path:
    """Resolve a path and verify it falls under an allowed root."""
    p = Path(path).expanduser().resolve()
    roots = _get_roots()
    for root in roots:
        try:
            p.relative_to(root)
            return p
        except ValueError:
            continue
    allowed = ", ".join(str(r) for r in roots)
    raise ValueError(f"Access denied: '{p}' is outside allowed roots ({allowed})")


def _fmt_size(size: int | float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} {unit}"
        size /= 1024  # type: ignore[assignment]
    return f"{size:.1f} PB"


def _fmt_time(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def _fmt_mode(mode: int) -> str:
    return stat.filemode(mode)


# ---------------------------------------------------------------------------
# Read-only tools
# ---------------------------------------------------------------------------


@tool(
    "Read a file and return its contents",
    read_only=True,
    destructive=False,
    idempotent=True,
)
def fs_read(
    path: Annotated[str, "Path to the file"],
    offset: Annotated[int, "Line offset to start from (0-based)"] = 0,
    limit: Annotated[int, "Max number of lines to return (0 = all)"] = 0,
    encoding: Annotated[str, "File encoding"] = "utf-8",
) -> str:
    p = _resolve(path)
    if not p.is_file():
        raise FileNotFoundError(f"Not a file: {p}")
    lines = p.read_text(encoding=encoding).splitlines(keepends=True)
    if offset:
        lines = lines[offset:]
    if limit:
        lines = lines[:limit]
    return "".join(lines)


@tool(
    "List directory contents",
    read_only=True,
    destructive=False,
    idempotent=True,
)
def fs_ls(
    path: Annotated[str, "Directory path"] = ".",
    all: Annotated[bool, "Include hidden files"] = False,
    long: Annotated[bool, "Show detailed info (size, mtime, permissions)"] = False,
) -> str:
    p = _resolve(path)
    if not p.is_dir():
        raise NotADirectoryError(f"Not a directory: {p}")
    entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
    if not all:
        entries = [e for e in entries if not e.name.startswith(".")]
    lines: list[str] = []
    for e in entries:
        if long:
            try:
                st = e.stat()
                lines.append(
                    f"{_fmt_mode(st.st_mode)}  {_fmt_size(st.st_size):>10}  "
                    f"{_fmt_time(st.st_mtime)}  {e.name}{'/' if e.is_dir() else ''}"
                )
            except OSError:
                lines.append(f"??????????  {'?':>10}  {'?':19}  {e.name}")
        else:
            lines.append(f"{e.name}{'/' if e.is_dir() else ''}")
    return "\n".join(lines) if lines else "(empty directory)"


@tool(
    "Get file or directory metadata (size, timestamps, permissions)",
    read_only=True,
    destructive=False,
    idempotent=True,
)
def fs_stat(
    path: Annotated[str, "Path to file or directory"],
) -> str:
    p = _resolve(path)
    if not p.exists():
        raise FileNotFoundError(f"Not found: {p}")
    st = p.stat()
    kind = "directory" if p.is_dir() else "symlink" if p.is_symlink() else "file"
    lines = [
        f"path: {p}",
        f"type: {kind}",
        f"size: {_fmt_size(st.st_size)} ({st.st_size} bytes)",
        f"permissions: {_fmt_mode(st.st_mode)}",
        f"owner: {st.st_uid}:{st.st_gid}",
        f"created: {_fmt_time(st.st_ctime)}",
        f"modified: {_fmt_time(st.st_mtime)}",
        f"accessed: {_fmt_time(st.st_atime)}",
        f"inode: {st.st_ino}",
        f"links: {st.st_nlink}",
    ]
    return "\n".join(lines)


@tool(
    "Search for files by name pattern (glob) in a directory tree",
    read_only=True,
    destructive=False,
    idempotent=True,
)
def fs_find(
    path: Annotated[str, "Root directory to search from"] = ".",
    pattern: Annotated[str, "Glob pattern to match (e.g. '*.py', '**/*.json')"] = "*",
    type: Annotated[str, "Filter: 'f' for files, 'd' for dirs, '' for all"] = "",
    max_depth: Annotated[int, "Max directory depth (0 = unlimited)"] = 0,
) -> str:
    p = _resolve(path)
    if not p.is_dir():
        raise NotADirectoryError(f"Not a directory: {p}")

    results: list[str] = []
    for match in p.rglob(pattern) if "**" in pattern else p.rglob(pattern):
        if type == "f" and not match.is_file():
            continue
        if type == "d" and not match.is_dir():
            continue
        if max_depth:
            try:
                depth = len(match.relative_to(p).parts)
                if depth > max_depth:
                    continue
            except ValueError:
                continue
        # Verify still under allowed roots
        try:
            _resolve(str(match))
        except ValueError:
            continue
        results.append(str(match.relative_to(p)))
    return "\n".join(sorted(results)) if results else "(no matches)"


@tool(
    "Search file contents using grep",
    read_only=True,
    destructive=False,
    idempotent=True,
)
def fs_grep(
    pattern: Annotated[str, "Regex pattern to search for"],
    path: Annotated[str, "File or directory to search in"] = ".",
    include: Annotated[str, "Glob pattern for filenames to include (e.g. '*.py')"] = "",
    recursive: Annotated[bool, "Search directories recursively"] = True,
    ignore_case: Annotated[bool, "Case-insensitive search"] = False,
    max_count: Annotated[int, "Max matches per file (0 = unlimited)"] = 0,
) -> Cmd:
    args = ["grep", "--color=never", "-n"]
    if recursive:
        args.append("-r")
    if ignore_case:
        args.append("-i")
    if max_count:
        args.extend(["-m", str(max_count)])
    if include:
        args.extend(["--include", include])
    args.extend([pattern, _resolve(path).as_posix()])
    return Cmd(*args)


@tool(
    "List allowed filesystem roots",
    read_only=True,
    destructive=False,
    idempotent=True,
)
def fs_roots() -> str:
    roots = _get_roots()
    return "\n".join(str(r) for r in roots)


# ---------------------------------------------------------------------------
# Write tools
# ---------------------------------------------------------------------------


@tool(
    "Write content to a file (creates parent directories if needed)",
    read_only=False,
    destructive=True,
    idempotent=True,
)
def fs_write(
    path: Annotated[str, "Path to the file"],
    content: Annotated[str, "Content to write"],
    append: Annotated[bool, "Append instead of overwrite"] = False,
    encoding: Annotated[str, "File encoding"] = "utf-8",
) -> str:
    p = _resolve(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if append:
        with p.open("a", encoding=encoding) as f:
            f.write(content)
    else:
        p.write_text(content, encoding=encoding)
    return f"Wrote {len(content)} chars to {p}"


@tool(
    "Create a directory (and parents if needed)",
    read_only=False,
    destructive=False,
    idempotent=True,
)
def fs_mkdir(
    path: Annotated[str, "Directory path to create"],
) -> str:
    p = _resolve(path)
    p.mkdir(parents=True, exist_ok=True)
    return f"Created {p}"


@tool(
    "Delete a file or empty directory",
    read_only=False,
    destructive=True,
    idempotent=True,
)
def fs_rm(
    path: Annotated[str, "Path to delete"],
    recursive: Annotated[bool, "Recursively delete directory contents"] = False,
) -> str:
    p = _resolve(path)
    if not p.exists():
        raise FileNotFoundError(f"Not found: {p}")
    if p.is_dir():
        if recursive:
            import shutil
            shutil.rmtree(p)
        else:
            p.rmdir()  # fails if not empty
    else:
        p.unlink()
    return f"Deleted {p}"


@tool(
    "Move or rename a file or directory",
    read_only=False,
    destructive=True,
    idempotent=False,
)
def fs_mv(
    src: Annotated[str, "Source path"],
    dst: Annotated[str, "Destination path"],
) -> str:
    s = _resolve(src)
    d = _resolve(dst)
    if not s.exists():
        raise FileNotFoundError(f"Source not found: {s}")
    s.rename(d)
    return f"Moved {s} -> {d}"


@tool(
    "Copy a file or directory",
    read_only=False,
    destructive=False,
    idempotent=True,
)
def fs_cp(
    src: Annotated[str, "Source path"],
    dst: Annotated[str, "Destination path"],
    recursive: Annotated[bool, "Copy directories recursively"] = False,
) -> str:
    import shutil
    s = _resolve(src)
    d = _resolve(dst)
    if not s.exists():
        raise FileNotFoundError(f"Source not found: {s}")
    if s.is_dir():
        if not recursive:
            raise IsADirectoryError(f"Use recursive=true to copy directories: {s}")
        shutil.copytree(s, d)
    else:
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)
    return f"Copied {s} -> {d}"
