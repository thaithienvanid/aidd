"""Rename the delivery team to the development team, as one pass over the tracked files.

The team is called the development team: the phrase "delivery team" (singular and plural, any case) becomes "development team",
the field `delivery_team` becomes `development_team`, the config key `delivery_teams` becomes `development_teams`, and the flag
`--delivery-team` becomes `--development-team`, with identifiers built from them (`in_delivery_team`, `delivery_team_problems`,
`config-delivery_teams`, `test_delivery_teams`). It leaves `delivery-manager`, `client-delivery`, `delivery` on its own, and
`aidd-team` untouched.

What it does not write, a person does: moving the glossary's `Delivery team` row and index entry to where `Development team`
belongs in alphabetical order, adding the one sentence that the development team is all the team's roles, keeping the two
negative validation tests that check `aidd validate` refuses `delivery_teams` and `delivery_team`, and re-running `aidd gen-docs`
after schemas change. It is a record of the first pass over `marron`.

Run `python3 tools/rename_development_team.py` once, from anywhere, on the commit before the rename. It finds the repository from
its own path, moves the two module and test files with git, updates tracked text files, and prints the counts for each form.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

MOVES = {
    "src/aidd/config/delivery_teams.py": "src/aidd/config/development_teams.py",
    "tests/test_delivery_teams.py": "tests/test_development_teams.py",
}
KINDS = (".py", ".json", ".jsonl", ".md", ".yaml", ".yml", ".sh", ".svg", ".txt", ".toml", ".html", ".js", ".css")
SKIP = (
    ".claude/settings.json",
    "opencode.json",
    ".codex/",
    "tools/rename_development_team.py",
)
PATTERN = re.compile(r"(--)?([Dd][Ee][Ll][Ii][Vv][Ee][Rr][Yy])([ _-][Tt][Ee][Aa][Mm][Ss]?)")


def tracked(root: Path) -> list[str]:
    """Every tracked path in `root`."""
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True).stdout.decode("utf-8")
    return [p for p in out.split("\0") if p]


def _word(delivery: str) -> str:
    if delivery.isupper():
        return "DEVELOPMENT"
    if delivery[:1].isupper():
        return "Development"
    return "development"


def _form(prefix: str, sep_and_team: str) -> str:
    low = (prefix + sep_and_team).lower()
    if prefix == "--":
        return "--delivery-team"
    if low == "_teams":
        return "delivery_teams"
    if low == "_team":
        return "delivery_team"
    return "phrase/hyphen"


def rename(text: str) -> tuple[str, Counter[str]]:
    """Replace every matching form in `text`, returning the new text and the count per form."""
    counts: Counter[str] = Counter()

    def sub(match: re.Match[str]) -> str:
        prefix, word, tail = match.group(1) or "", match.group(2), match.group(3)
        counts[_form(prefix, tail)] += 1
        return f"{prefix}{_word(word)}{tail}"

    return PATTERN.sub(sub, text), counts


def main() -> int:
    """Move renamed modules and sweep tracked files in the repository."""
    root = Path(__file__).resolve().parent.parent
    for old, new in MOVES.items():
        if (root / old).exists():
            subprocess.run(["git", "mv", old, new], cwd=root, check=True)
    totals: Counter[str] = Counter()
    changed = 0
    for rel in tracked(root):
        if not rel.endswith(KINDS) or rel.startswith(SKIP) or rel in SKIP:
            continue
        path = root / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        updated, counts = rename(text)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            totals += counts
            changed += 1
    print(f"{changed} files changed, {sum(totals.values())} renames: {dict(totals)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
