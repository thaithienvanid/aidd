"""Rename the top-level `loop` key, `loop.md`, and `loop_*` test helpers/fixtures to `graph`."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

KEY_FIELDS = (
    "version|steps|stages|gates|entry|routes|flows|loops|documents|capabilities|"
    "artifacts|handoffs|contract|lead|decision_rights|merge_approval|review_report|"
    "file_skills|shared_rules|autopilot"
)

COMMON_SUBS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r'\["loop"\]'), '["graph"]'),
    (re.compile(r"\['loop'\]"), "['graph']"),
    (re.compile(r"properties/loop\b"), "properties/graph"),
    (re.compile(rf"\bloop\.({KEY_FIELDS})\b"), r"graph.\1"),
    (re.compile(r"\bloop\.md\b"), "graph.md"),
    (re.compile(r"\bloop_cases\b"), "graph_cases"),
    (re.compile(r"\bloop_repo\b"), "graph_repo"),
    (re.compile(r"\bloop_contract\b"), "graph_contract"),
]


def _rewrite_roles_json(text: str) -> str:
    return text.replace('  "loop": {\n', '  "graph": {\n', 1)


def _rewrite_roles_schema(text: str) -> str:
    text = text.replace('    "loop",\n', '    "graph",\n', 1)
    return text.replace('    "loop": {\n', '    "graph": {\n', 1)


def main() -> int:
    tracked = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()
    changed = 0
    for rel in tracked:
        if rel in ("tools/rename_loop_to_graph.py", "tests/fixtures/design/pins.json"):
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        updated = original
        if rel == "schemas/roles.json":
            updated = _rewrite_roles_json(updated)
        elif rel == "schemas/roles.schema.json":
            updated = _rewrite_roles_schema(updated)
        for pattern, replacement in COMMON_SUBS:
            updated = pattern.sub(replacement, updated)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed += 1
    print(f"updated {changed} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
