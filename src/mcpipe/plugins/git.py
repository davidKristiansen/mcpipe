"""Git plugin for mcpipe."""

from __future__ import annotations

from typing import Annotated

from mcpipe import Cmd, tool

# Default number of context lines in diff output.
DEFAULT_CONTEXT_LINES = 3


def _git(*args: str, repo_path: str = ".") -> Cmd:
    """Build a git Cmd with -C repo_path prefix."""
    return Cmd("git", "-C", repo_path, *args)


def _validate_ref(value: str, label: str = "value") -> None:
    """Reject refs starting with '-' to prevent flag injection."""
    if value.startswith("-"):
        raise ValueError(f"Invalid {label}: '{value}' — cannot start with '-'")


# ---------------------------------------------------------------------------
# Read-only tools
# ---------------------------------------------------------------------------


@tool(
    "Shows the working tree status",
    read_only=True,
    destructive=False,
    idempotent=True,
)
def git_status(
    repo_path: Annotated[str, "Path to the git repository"] = ".",
) -> Cmd:
    return _git("status", repo_path=repo_path)


@tool(
    "Show commit log",
    read_only=True,
    destructive=False,
    idempotent=True,
)
def git_log(
    repo_path: Annotated[str, "Path to the git repository"] = ".",
    max_count: Annotated[int, "Number of commits to show"] = 10,
    since: Annotated[str, "Show commits after this date (e.g. '1 week ago')"] = "",
    until: Annotated[str, "Show commits before this date (e.g. '2024-01-15')"] = "",
    path: Annotated[str, "Limit to commits touching this path"] = "",
) -> Cmd:
    args = ["log", f"--max-count={max_count}"]
    if since:
        _validate_ref(since, "since")
        args.extend(["--since", since])
    if until:
        _validate_ref(until, "until")
        args.extend(["--until", until])
    if path:
        args.extend(["--", path])
    return _git(*args, repo_path=repo_path)


@tool(
    "Shows changes in the working directory that are not yet staged",
    read_only=True,
    destructive=False,
    idempotent=True,
)
def git_diff_unstaged(
    repo_path: Annotated[str, "Path to the git repository"] = ".",
    context_lines: Annotated[
        int, "Number of context lines around changes"
    ] = DEFAULT_CONTEXT_LINES,  # noqa: E501
) -> Cmd:
    return _git("diff", f"--unified={context_lines}", repo_path=repo_path)


@tool(
    "Shows changes that are staged for commit",
    read_only=True,
    destructive=False,
    idempotent=True,
)
def git_diff_staged(
    repo_path: Annotated[str, "Path to the git repository"] = ".",
    context_lines: Annotated[
        int, "Number of context lines around changes"
    ] = DEFAULT_CONTEXT_LINES,  # noqa: E501
) -> Cmd:
    return _git("diff", f"--unified={context_lines}", "--cached", repo_path=repo_path)


@tool(
    "Shows differences between branches or commits",
    read_only=True,
    destructive=False,
    idempotent=True,
)
def git_diff(
    repo_path: Annotated[str, "Path to the git repository"] = ".",
    target: Annotated[str, "Branch, commit, or ref to diff against"] = "",
    context_lines: Annotated[
        int, "Number of context lines around changes"
    ] = DEFAULT_CONTEXT_LINES,  # noqa: E501
) -> Cmd:
    _validate_ref(target, "target")
    return _git("diff", f"--unified={context_lines}", target, repo_path=repo_path)


@tool(
    "Shows the contents of a commit",
    read_only=True,
    destructive=False,
    idempotent=True,
)
def git_show(
    repo_path: Annotated[str, "Path to the git repository"] = ".",
    revision: Annotated[str, "Commit hash, branch, or ref to show"] = "HEAD",
) -> Cmd:
    _validate_ref(revision, "revision")
    return _git("show", revision, repo_path=repo_path)


@tool(
    "List git branches",
    read_only=True,
    destructive=False,
    idempotent=True,
)
def git_branch(
    repo_path: Annotated[str, "Path to the git repository"] = ".",
    branch_type: Annotated[
        str, "Which branches: 'local', 'remote', or 'all'"
    ] = "local",  # noqa: E501
    contains: Annotated[str, "Only branches containing this commit SHA"] = "",
    not_contains: Annotated[str, "Only branches NOT containing this commit SHA"] = "",
) -> Cmd:
    if contains:
        _validate_ref(contains, "contains")
    if not_contains:
        _validate_ref(not_contains, "not_contains")

    args: list[str] = ["branch"]
    match branch_type:
        case "remote":
            args.append("-r")
        case "all":
            args.append("-a")
        case "local":
            pass
        case _:
            raise ValueError(
                f"Invalid branch_type: '{branch_type}'. Use 'local', 'remote', or 'all'"
            )  # noqa: E501

    if contains:
        args.extend(["--contains", contains])
    if not_contains:
        args.extend(["--no-contains", not_contains])

    return _git(*args, repo_path=repo_path)


# ---------------------------------------------------------------------------
# Write tools
# ---------------------------------------------------------------------------


@tool(
    "Adds file contents to the staging area",
    read_only=False,
    destructive=False,
    idempotent=True,
)
def git_add(
    repo_path: Annotated[str, "Path to the git repository"] = ".",
    files: Annotated[str, "Comma-separated file paths to stage, or '.' for all"] = ".",
) -> Cmd:
    file_list = [f.strip() for f in files.split(",")]
    # Use '--' to prevent files starting with '-' from being interpreted as options
    return _git("add", "--", *file_list, repo_path=repo_path)


@tool(
    "Records changes to the repository",
    read_only=False,
    destructive=False,
    idempotent=False,
)
def git_commit(
    repo_path: Annotated[str, "Path to the git repository"] = ".",
    message: Annotated[str, "Commit message"] = "",
) -> Cmd:
    if not message:
        raise ValueError("Commit message is required")
    return _git("commit", "-m", message, repo_path=repo_path)


@tool(
    "Unstages all staged changes",
    read_only=False,
    destructive=True,
    idempotent=True,
)
def git_reset(
    repo_path: Annotated[str, "Path to the git repository"] = ".",
) -> Cmd:
    return _git("reset", repo_path=repo_path)


@tool(
    "Creates a new branch from an optional base branch",
    read_only=False,
    destructive=False,
    idempotent=False,
)
def git_create_branch(
    repo_path: Annotated[str, "Path to the git repository"] = ".",
    branch_name: Annotated[str, "Name of the new branch"] = "",
    base_branch: Annotated[
        str, "Base branch to create from (default: current branch)"
    ] = "",  # noqa: E501
) -> Cmd:
    if not branch_name:
        raise ValueError("Branch name is required")
    _validate_ref(branch_name, "branch_name")
    if base_branch:
        _validate_ref(base_branch, "base_branch")

    args = ["branch", branch_name]
    if base_branch:
        args.append(base_branch)
    return _git(*args, repo_path=repo_path)


@tool(
    "Switches branches",
    read_only=False,
    destructive=False,
    idempotent=False,
)
def git_checkout(
    repo_path: Annotated[str, "Path to the git repository"] = ".",
    branch_name: Annotated[str, "Branch name to switch to"] = "",
) -> Cmd:
    if not branch_name:
        raise ValueError("Branch name is required")
    _validate_ref(branch_name, "branch_name")
    return _git("checkout", branch_name, repo_path=repo_path)


# ---------------------------------------------------------------------------
# Remote tools
# ---------------------------------------------------------------------------


@tool(
    "Fetch refs and objects from a remote",
    read_only=False,
    destructive=False,
    idempotent=True,
)
def git_fetch(
    repo_path: Annotated[str, "Path to the git repository"] = ".",
    remote: Annotated[str, "Remote name (e.g. 'origin')"] = "",
    prune: Annotated[bool, "Remove remote-tracking refs that no longer exist"] = False,
    all: Annotated[bool, "Fetch all remotes"] = False,
) -> Cmd:
    args: list[str] = ["fetch"]
    if all:
        args.append("--all")
    if prune:
        args.append("--prune")
    if remote and not all:
        _validate_ref(remote, "remote")
        args.append(remote)
    return _git(*args, repo_path=repo_path)


@tool(
    "Pull changes from a remote branch",
    read_only=False,
    destructive=False,
    idempotent=False,
)
def git_pull(
    repo_path: Annotated[str, "Path to the git repository"] = ".",
    remote: Annotated[str, "Remote name"] = "",
    branch: Annotated[str, "Branch name"] = "",
    rebase: Annotated[bool, "Rebase instead of merge"] = False,
) -> Cmd:
    args: list[str] = ["pull"]
    if rebase:
        args.append("--rebase")
    if remote:
        _validate_ref(remote, "remote")
        args.append(remote)
        if branch:
            _validate_ref(branch, "branch")
            args.append(branch)
    return _git(*args, repo_path=repo_path)


@tool(
    "Push commits to a remote branch",
    read_only=False,
    destructive=False,
    idempotent=False,
)
def git_push(
    repo_path: Annotated[str, "Path to the git repository"] = ".",
    remote: Annotated[str, "Remote name"] = "",
    branch: Annotated[str, "Branch name"] = "",
    set_upstream: Annotated[bool, "Set upstream tracking (-u)"] = False,
    tags: Annotated[bool, "Push tags"] = False,
) -> Cmd:
    args: list[str] = ["push"]
    if set_upstream:
        args.append("-u")
    if tags:
        args.append("--tags")
    if remote:
        _validate_ref(remote, "remote")
        args.append(remote)
        if branch:
            _validate_ref(branch, "branch")
            args.append(branch)
    return _git(*args, repo_path=repo_path)


# ---------------------------------------------------------------------------
# Stash tools
# ---------------------------------------------------------------------------


@tool(
    "Stash working directory changes",
    read_only=False,
    destructive=False,
    idempotent=False,
)
def git_stash_push(
    repo_path: Annotated[str, "Path to the git repository"] = ".",
    message: Annotated[str, "Stash message"] = "",
    include_untracked: Annotated[bool, "Include untracked files"] = False,
) -> Cmd:
    args: list[str] = ["stash", "push"]
    if message:
        args.extend(["-m", message])
    if include_untracked:
        args.append("--include-untracked")
    return _git(*args, repo_path=repo_path)


@tool(
    "Apply and remove the most recent stash",
    read_only=False,
    destructive=False,
    idempotent=False,
)
def git_stash_pop(
    repo_path: Annotated[str, "Path to the git repository"] = ".",
    index: Annotated[int, "Stash index to pop (0 = most recent)"] = 0,
) -> Cmd:
    return _git("stash", "pop", f"stash@{{{index}}}", repo_path=repo_path)


@tool(
    "List stashed changes",
    read_only=True,
    destructive=False,
    idempotent=True,
)
def git_stash_list(
    repo_path: Annotated[str, "Path to the git repository"] = ".",
) -> Cmd:
    return _git("stash", "list", repo_path=repo_path)


# ---------------------------------------------------------------------------
# Tag tools
# ---------------------------------------------------------------------------


@tool(
    "List or create tags",
    read_only=False,
    destructive=False,
    idempotent=True,
)
def git_tag(
    repo_path: Annotated[str, "Path to the git repository"] = ".",
    name: Annotated[str, "Tag name to create (omit to list tags)"] = "",
    message: Annotated[str, "Annotated tag message (creates annotated tag)"] = "",
    ref: Annotated[str, "Commit to tag (default: HEAD)"] = "",
) -> Cmd:
    if not name:
        return _git("tag", "--list", repo_path=repo_path)
    _validate_ref(name, "name")
    args: list[str] = ["tag"]
    if message:
        args.extend(["-a", name, "-m", message])
    else:
        args.append(name)
    if ref:
        _validate_ref(ref, "ref")
        args.append(ref)
    return _git(*args, repo_path=repo_path)


# ---------------------------------------------------------------------------
# History rewrite tools
# ---------------------------------------------------------------------------


@tool(
    "Show who last modified each line of a file",
    read_only=True,
    destructive=False,
    idempotent=True,
)
def git_blame(
    repo_path: Annotated[str, "Path to the git repository"] = ".",
    file: Annotated[str, "File path to blame"] = "",
    line_start: Annotated[int, "Start line (0 to skip)"] = 0,
    line_end: Annotated[int, "End line (0 to skip)"] = 0,
) -> Cmd:
    if not file:
        raise ValueError("File path is required")
    args: list[str] = ["blame"]
    if line_start and line_end:
        args.extend(["-L", f"{line_start},{line_end}"])
    args.extend(["--", file])
    return _git(*args, repo_path=repo_path)


@tool(
    "Apply a commit from another branch onto the current branch",
    read_only=False,
    destructive=False,
    idempotent=False,
)
def git_cherry_pick(
    repo_path: Annotated[str, "Path to the git repository"] = ".",
    commit: Annotated[str, "Commit hash to cherry-pick"] = "",
    no_commit: Annotated[bool, "Apply changes without committing"] = False,
) -> Cmd:
    if not commit:
        raise ValueError("Commit hash is required")
    _validate_ref(commit, "commit")
    args: list[str] = ["cherry-pick"]
    if no_commit:
        args.append("--no-commit")
    args.append(commit)
    return _git(*args, repo_path=repo_path)


@tool(
    "Revert a commit by creating a new commit that undoes it",
    read_only=False,
    destructive=False,
    idempotent=False,
)
def git_revert(
    repo_path: Annotated[str, "Path to the git repository"] = ".",
    commit: Annotated[str, "Commit hash to revert"] = "",
    no_commit: Annotated[bool, "Apply changes without committing"] = False,
) -> Cmd:
    if not commit:
        raise ValueError("Commit hash is required")
    _validate_ref(commit, "commit")
    args: list[str] = ["revert"]
    if no_commit:
        args.append("--no-commit")
    args.append(commit)
    return _git(*args, repo_path=repo_path)


@tool(
    "Show remote repositories",
    read_only=True,
    destructive=False,
    idempotent=True,
)
def git_remote(
    repo_path: Annotated[str, "Path to the git repository"] = ".",
    verbose: Annotated[bool, "Show URLs"] = True,
) -> Cmd:
    args: list[str] = ["remote"]
    if verbose:
        args.append("-v")
    return _git(*args, repo_path=repo_path)


@tool(
    "Merge a branch into the current branch",
    read_only=False,
    destructive=False,
    idempotent=False,
)
def git_merge(
    repo_path: Annotated[str, "Path to the git repository"] = ".",
    branch: Annotated[str, "Branch to merge"] = "",
    no_ff: Annotated[bool, "Create a merge commit even for fast-forward"] = False,
    message: Annotated[str, "Merge commit message"] = "",
) -> Cmd:
    if not branch:
        raise ValueError("Branch name is required")
    _validate_ref(branch, "branch")
    args: list[str] = ["merge"]
    if no_ff:
        args.append("--no-ff")
    if message:
        args.extend(["-m", message])
    args.append(branch)
    return _git(*args, repo_path=repo_path)
