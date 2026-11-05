"""A name is defined once and read by what needs it. Three checks over the source:

- a list of work-item types is a named constant, never spelled again inline, so adding a type touches one definition;
- a package door exports only names something outside the package reads (a test counts);
- a module-level constant is read somewhere (a load of the name, an attribute of that name, or an import);
- a comment says what a thing is, never the id of a backlog row, which ages as rows close."""

import ast
import re
import unittest
from pathlib import Path

from helpers import ROOT

SRC = ROOT / "src" / "aidd"
ALL_CODE = [SRC, ROOT / "tests", ROOT / "plugins" / "aidd-team" / "tools", ROOT / "tools"]
# The sets of work-item types that have a named constant; the same set spelled inline is the finding.
TYPE_SETS = ({"spec", "intent"}, {"spec", "intent", "proposal"})


def python_files(*roots: Path) -> list[Path]:
    return sorted(p for r in roots if r.exists() for p in r.rglob("*.py") if "__pycache__" not in p.parts)


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def string_set(node: ast.AST) -> set[str] | None:
    if isinstance(node, ast.Tuple | ast.List | ast.Set) and node.elts and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in node.elts):
        return {e.value for e in node.elts}  # type: ignore[attr-defined]
    return None


class NamedThings(unittest.TestCase):
    def test_a_set_of_work_item_types_is_spelled_once_as_a_constant(self):
        found = []
        for path in python_files(SRC):
            tree = parse(path)
            defined = {id(node.value) for node in tree.body if isinstance(node, ast.Assign | ast.AnnAssign) and node.value is not None}
            for node in ast.walk(tree):
                if string_set(node) in TYPE_SETS and id(node) not in defined:
                    found.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}")
        self.assertEqual(found, [], "use the constant (`workitems.WORK_TYPES`, or the definition that names this set) and not an inline copy")

    def test_every_door_name_is_read_outside_its_package(self):
        text = {p: p.read_text(encoding="utf-8") for p in python_files(*ALL_CODE)}
        unused = []
        for door in sorted(SRC.glob("*/__init__.py")):
            package = door.parent
            exports = [
                e.value
                for node in parse(door).body
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
                for e in node.value.elts  # type: ignore[attr-defined]
            ]
            outside = [t for p, t in text.items() if package not in p.parents]
            for name in exports:
                if not any(name in t for t in outside):
                    unused.append(f"{package.name}.{name}")
        self.assertEqual(unused, [], "a door exports only what another package or a test reads; drop the name from `__all__`, its import, and its map entry")

    def test_every_module_constant_is_read_somewhere(self):
        loads: set[str] = set()
        for path in python_files(*ALL_CODE):
            for node in ast.walk(parse(path)):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    loads.add(node.id)
                elif isinstance(node, ast.Attribute):
                    loads.add(node.attr)
                elif isinstance(node, ast.alias):
                    loads.add(node.name.split(".")[-1])
        unread = []
        for path in python_files(SRC):
            for node in parse(path).body:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
                for t in targets:
                    if isinstance(t, ast.Name) and t.id.isupper() and not t.id.startswith("_") and t.id not in loads and t.id != "__all__":
                        unread.append(f"{path.relative_to(ROOT).as_posix()}:{t.id}")
        self.assertEqual(unread, [], "delete a constant nothing reads, or use it where it belongs")

    def test_no_comment_in_the_source_names_a_backlog_row(self):
        row = re.compile(r"\bR\d{2,3}[a-z]?\b")
        found = []
        for root in (SRC, ROOT / "plugins" / "aidd-team" / "tools"):
            for path in sorted(p for p in root.rglob("*") if p.suffix in (".py", ".css", ".js") and "__pycache__" not in p.parts):
                found += [
                    f"{path.relative_to(ROOT).as_posix()}:{n}" for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1) if row.search(line)
                ]
        self.assertEqual(found, [], "say what the row asked for, not its id")


if __name__ == "__main__":
    unittest.main()
