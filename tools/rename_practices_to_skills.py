"""Rename the `practices` key of `schemas/roles.json` to `skills`, and the `graph` list named for files to `file_skills`.

The key sits in three places: the top-level catalogue, each role's list, and each entry of `graph.file_*`. The kind keeps
its name in prose ("practice skill"), in the `roles:practices` and `count:practices` generated tokens, and in local names
that hold practice skills. Run it twice and the second run changes nothing.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

OLD, NEW = "practices", "skills"
FILE_OLD, FILE_NEW = f"file_{OLD}", f"file_{NEW}"
PLACEHOLDER_OLD, PLACEHOLDER_NEW = FILE_OLD.upper(), FILE_NEW.upper()

SELF = "tools/rename_practices_to_skills.py"
# The file that owns the count token named for the kind, and the one test line that maps that token's label.
KEPT_FILES = frozenset({SELF, "src/aidd/docsgen/counts.py"})
KEPT_LINES = ('"practice skills": "practices"',)

ROLES_JSON, ROLES_SCHEMA = "schemas/roles.json", "schemas/roles.schema.json"

# A JSON key at the start of a line, as roles.json holds it, and a quoted key or name anywhere in the schema and the code.
JSON_KEY = re.compile(rf'^(\s*)"{OLD}":', re.MULTILINE)
QUOTED = re.compile(rf"""(["'])(/?){OLD}\1""")
# A backticked key in prose or in a message, with a path below it: `practices` or `practices.<name>.standards`.
BACKTICKED = re.compile(rf"`{OLD}(?=[.`])")


def _file_names(text: str) -> str:
    return text.replace(FILE_OLD, FILE_NEW).replace(PLACEHOLDER_OLD, PLACEHOLDER_NEW)


def _quoted(match: re.Match[str]) -> str:
    return f"{match[1]}{match[2]}{NEW}{match[1]}"


def _rewrite_roles_json(text: str) -> str:
    return _file_names(JSON_KEY.sub(rf'\1"{NEW}":', text))


def _rewrite_code(text: str) -> str:
    out = []
    for line in text.splitlines(keepends=True):
        if not any(kept in line for kept in KEPT_LINES):
            line = BACKTICKED.sub(f"`{NEW}", QUOTED.sub(_quoted, line))
        out.append(_file_names(line))
    return "".join(out)


def _rewrite_schema(text: str) -> str:
    return _file_names(BACKTICKED.sub(f"`{NEW}", QUOTED.sub(_quoted, text)))


def _rewrite_doc(text: str) -> str:
    return _file_names(BACKTICKED.sub(f"`{NEW}", text))


def _pointers(node: object, names: tuple[str, ...], where: str = "") -> list[str]:
    """The JSON pointers whose last segment is one of `names`."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{where}/{key}"
            if key in names:
                found.append(here)
            found += _pointers(value, names, here)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            found += _pointers(value, names, f"{where}/{i}")
    return found


def _rename_in_data(path: Path) -> None:
    """Fail unless the data holds the same keys at the same pointers, under the new names."""
    old_names, new_names = (OLD, FILE_OLD), (NEW, FILE_NEW)
    before = _pointers(json.loads(path.read_text(encoding="utf-8")), old_names)
    text = path.read_text(encoding="utf-8")
    path.write_text(_rewrite_roles_json(text), encoding="utf-8")
    tree = json.loads(path.read_text(encoding="utf-8"))
    after = _pointers(tree, new_names)
    renamed = {OLD: NEW, FILE_OLD: FILE_NEW}
    expected = ["/".join(renamed.get(part, part) for part in p.split("/")) for p in before]
    if before and (_pointers(tree, old_names) or sorted(after) != sorted(expected)):
        raise SystemExit(f"{path}: the keys did not move as their pointers say they should")
    print(f"{path.name}: {len(before)} key(s) renamed by pointer")


def main() -> int:
    tracked = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()
    changed = 0
    for rel in tracked:
        if rel in KEPT_FILES:
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        if rel == ROLES_JSON:
            before = path.read_text(encoding="utf-8")
            _rename_in_data(path)
            changed += path.read_text(encoding="utf-8") != before
            continue
        if rel == ROLES_SCHEMA:
            rewrite = _rewrite_schema
        elif path.suffix == ".py":
            rewrite = _rewrite_code
        elif path.suffix == ".md":
            rewrite = _rewrite_doc
        else:
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        updated = rewrite(original)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            print(f"changed {rel}")
            changed += 1
    print(f"updated {changed} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
