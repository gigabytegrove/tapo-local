#!/usr/bin/env python3
"""Generate release notes from the section matching the manifest version."""

from __future__ import annotations

import re
import sys
from pathlib import Path

HEADING = re.compile(r"^## ([0-9]+\.[0-9]+\.[0-9]+)\s*$", re.MULTILINE)


def render_release_notes(version: str, changelog: str) -> str:
    """Return Markdown for one exact version or raise a helpful error."""
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("Version must use X.Y.Z format")
    versions = list(HEADING.finditer(changelog))
    matches = [item for item in versions if item.group(1) == version]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one changelog section for {version}")
    entry = matches[0]
    next_entry = next(
        (item for item in versions if item.start() > entry.start()), None
    )
    content = changelog[
        entry.end():next_entry.start() if next_entry else None
    ].strip()
    if not content or not re.search(r"^\s*[-*] ", content, re.MULTILINE):
        raise ValueError(f"No release changes found for {version}")
    if any(word in content for word in ("redacted.invalid", "TODO", "TBD")):
        raise ValueError("Unresolved placeholders in release notes")
    return (
        f"# Tapo Local {version}\n\n"
        f"{content}\n\n"
        "## Helpful links\n\n"
        "- [Install and update](https://github.com/gigabytegrove/tapo-local#install-with-hacs)\n"
        "- [Supported devices](https://github.com/gigabytegrove/tapo-local/blob/main/SUPPORTED_DEVICES.md)\n"
        "- [Report a problem](https://github.com/gigabytegrove/tapo-local/issues/new/choose)\n"
        "- [Complete release history](https://github.com/gigabytegrove/tapo-local/blob/main/CHANGELOG.md)\n"
    )


def main(arguments: list[str]) -> int:
    if len(arguments) not in (2, 3):
        print("Usage: render_release_notes.py VERSION [CHANGELOG.md]", file=sys.stderr)
        return 2
    source = Path(arguments[2]) if len(arguments) == 3 else Path("CHANGELOG.md")
    try:
        notes = render_release_notes(
            arguments[1], source.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        print(f"Release notes not available: {exc}", file=sys.stderr)
        return 1
    print(notes, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
