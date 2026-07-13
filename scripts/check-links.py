#!/usr/bin/env python3
"""Verify that every relative markdown link in the skill resolves to a real file.

The skill works by dispatch: SKILL.md points at its reference files with relative
links, and each fix is loaded on demand the same way. `claude plugin validate`
checks manifest structure and skill frontmatter, but it does not follow these
cross-links, so a typo'd path is a silent runtime failure. The audit just cannot
load that reference and quietly degrades. This guard catches it in CI.

Exits non-zero if any relative link points at a missing file or directory.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Every markdown file whose links we hold to account: the skill and its
# references, plus the README (its links into the skill must stay valid too).
TARGETS = sorted(set((ROOT / "skills").rglob("*.md")) | {ROOT / "README.md"})

# [text](target) and ![alt](target). Group 1 is the target.
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")

EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "tel:", "#")


def is_external(target: str) -> bool:
    return target.startswith(EXTERNAL_PREFIXES)


def main() -> int:
    broken = []
    for md in TARGETS:
        if not md.exists():
            continue
        for lineno, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            for match in LINK_RE.finditer(line):
                target = match.group(1).strip()
                # Drop an optional "title": [x](path "title") -> path
                target = target.split(" ", 1)[0].strip()
                if not target or is_external(target):
                    continue
                # Drop an anchor: file.md#section -> file.md
                path_part = target.split("#", 1)[0]
                if not path_part:
                    continue
                resolved = (md.parent / path_part).resolve()
                if not resolved.exists():
                    broken.append((md.relative_to(ROOT), lineno, target))

    if broken:
        print("Broken relative links:\n")
        for path, lineno, target in broken:
            print(f"  {path}:{lineno}  ->  {target}")
        print(f"\n{len(broken)} broken link(s). Fix these before shipping.")
        return 1

    print(f"OK: all relative links resolve across {len(TARGETS)} markdown file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
