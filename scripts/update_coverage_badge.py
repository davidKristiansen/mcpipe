"""Update the coverage badge in README.md from coverage.xml."""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

COVERAGE_XML = Path("coverage.xml")
README = Path("README.md")

BADGE_PATTERN = re.compile(
    r"!\[coverage\]\(https://img\.shields\.io/badge/coverage-\d+%25-\w+\)"
)


def _color(pct: int) -> str:
    if pct >= 80:
        return "brightgreen"
    if pct >= 60:
        return "green"
    if pct >= 40:
        return "yellow"
    if pct >= 20:
        return "orange"
    return "red"


def main() -> int:
    if not COVERAGE_XML.exists():
        print("coverage.xml not found — run pytest first", file=sys.stderr)
        return 1

    tree = ET.parse(COVERAGE_XML)
    rate = float(tree.getroot().attrib["line-rate"])
    pct = int(rate * 100)
    color = _color(pct)

    badge = f"![coverage](https://img.shields.io/badge/coverage-{pct}%25-{color})"

    text = README.read_text()
    if not BADGE_PATTERN.search(text):
        print("coverage badge not found in README.md", file=sys.stderr)
        return 1

    updated = BADGE_PATTERN.sub(badge, text)
    if updated != text:
        README.write_text(updated)
        print(f"Updated coverage badge to {pct}%")
    else:
        print(f"Coverage badge already at {pct}%")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
