"""Regenerate the table of contents in README.md.

Finds the block between <!--toc:start--> and <!--toc:end--> and replaces it
with a TOC generated from markdown headings (## and below).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

README = Path("README.md")

# Matches ATX headings: ## Foo, ### Bar, etc. (not # h1)
_HEADING_RE = re.compile(r"^(#{2,6})\s+(.+)$")

# TOC sentinel markers
_TOC_START = "<!--toc:start-->"
_TOC_END = "<!--toc:end-->"


def _slug(text: str) -> str:
    """Convert heading text to GitHub-compatible anchor slug."""
    # Strip inline markdown: **bold**, *italic*, `code`, [link](url)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    # GitHub slug rules: lowercase, spaces→hyphens, strip non-alnum/hyphen
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    return slug


def _generate_toc(lines: list[str]) -> str:
    """Generate markdown TOC from heading lines."""
    entries: list[str] = []
    in_code_block = False

    for line in lines:
        stripped = line.rstrip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        m = _HEADING_RE.match(stripped)
        if not m:
            continue

        level = len(m.group(1))  # number of #'s
        text = m.group(2).strip()
        indent = "  " * (level - 2)
        entries.append(f"{indent}- [{text}](#{_slug(text)})")

    return "\n".join(entries)


def main() -> int:
    if not README.exists():
        print("README.md not found", file=sys.stderr)
        return 1

    text = README.read_text()

    start_idx = text.find(_TOC_START)
    end_idx = text.find(_TOC_END)
    if start_idx == -1 or end_idx == -1:
        print("TOC markers not found in README.md", file=sys.stderr)
        return 1

    # Parse headings from the full file (excluding the TOC block itself)
    before_toc = text[:start_idx]
    after_toc = text[end_idx + len(_TOC_END):]
    content_lines = (before_toc + after_toc).splitlines()

    toc = _generate_toc(content_lines)
    new_block = f"{_TOC_START}\n{toc}\n{_TOC_END}"

    updated = text[:start_idx] + new_block + text[end_idx + len(_TOC_END):]

    if updated != text:
        README.write_text(updated)
        print("Updated TOC in README.md")
    else:
        print("TOC already up to date")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
