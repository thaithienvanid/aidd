"""A name is defined once and read by what needs it. Three checks over the source:

- a list of work-item types is a named constant, never spelled again inline, so adding a type touches one definition;
- a package door exports only names something outside the package reads (a test counts);
- a module-level constant is read somewhere (a load of the name, an attribute of that name, or an import);
- a tracked text file says what holds now, never how it was built: no builder's name, plan or backlog id, or "raised from"."""

import ast
import re
import unittest
from pathlib import Path

from helpers import ROOT, repo_files

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


# What a reader who never saw the build must not meet in a tracked text file. A name is a word of its own: not part of a
# colour (`#b00`), an encoding name (`b64`, `b64decode`), or a version (`R2024a`). A builder's name is two digits after `b`,
# so a hex word such as `b429` is not one. A backlog row has two or three digits. A plan work package, a plan item, and a
# report name a place the reader cannot open. A history phrase says how a number or a name changed.
BUILD_HISTORY = {
    "a builder's name": re.compile(r"(?<![\w#-])b(?!64\b)\d{2}\b"),
    "a backlog row": re.compile(r"\bR\d{2,3}[a-z]?\b"),
    "a plan work package": re.compile(r"\b(?:WP|DM)-\d+[a-z]?\b"),
    "a plan item": re.compile(r"\bF\d+\.\d+\b"),
    "a report": re.compile(r"\breports? [a-z]\d{1,3}\b"),
    "a history phrase": re.compile(r"\b(?:raised|lowered|increased|decreased|bumped|renamed) from\b|\bunder redesign\b"),
}
# A UN regulation is named `UN R155`, and a chain of them (`UN R155 (title) and R156`) is spared by this rule, not by a list.
UN_REGULATIONS = re.compile(r"\bUN R\d{2,3}(?: \([^)]*\))?(?:,? and (?:UN )?R\d{2,3}(?: \([^)]*\))?)*")
# True exceptions, as (file, matched text): the reason says why the text is not history. Add a row only for a use that
# describes a thing as it is now, such as a release note that quotes a phrase the skill bans.
ACCEPTED: dict[tuple[str, str], str] = {
    ("CHANGELOG.md", "raised from"): "the release note quotes the phrase the maintainable-code skill bans",
    ("plugins/aidd-packs/skills/embedded-automotive-industrial/SKILL.md", "R155"): "UN Regulation No. 155, named without its prefix",
    ("plugins/aidd-packs/skills/embedded-automotive-industrial/SKILL.md", "R156"): "UN Regulation No. 156, named without its prefix",
    ("schemas/industry-standards.json", "R155"): "UN Regulation No. 155, named without its prefix",
    ("schemas/packs.json", "R155"): "UN Regulation No. 155, named without its prefix",
    ("schemas/packs.json", "R156"): "UN Regulation No. 156, named without its prefix",
    ("plugins/aidd-team/skills/maintainable-code/SKILL.md", "raised from"): "the skill names the phrase it bans",
    ("plugins/aidd-team/skills/maintainable-code/references/history.md", "raised from"): "the reference shows the phrase it bans, in a bad example",
    ("plugins/aidd-team/skills/maintainable-code/references/history.md", "lowered from"): "the reference names the phrase it bans",
}
# This file holds the pattern's words and its sample lines, so it is not read for them.
OWN_FILE = "tests/test_named_things.py"
HOW_TO_ACCEPT = (
    "say what holds and why, for a reader who never saw the build; history goes in the commit message. "
    "An honest use is a row of ACCEPTED in tests/test_named_things.py: the file, the matched text, and the reason"
)


def build_history(line: str) -> list[tuple[str, str]]:
    """The (kind, text) of each place a line names how it was built, once the UN regulations are set aside."""
    line = UN_REGULATIONS.sub("", line)
    return [(kind, match.group(0)) for kind, pattern in BUILD_HISTORY.items() for match in pattern.finditer(line)]


def tracked_text(name: str) -> str | None:
    """The text of a tracked file, or None for a file that is gone or not UTF-8 text."""
    try:
        return (ROOT / name).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


class NamedThings(unittest.TestCase):
    maxDiff = None

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

    def test_no_tracked_text_names_how_it_was_built(self):
        found = []
        for name in repo_files():
            text = tracked_text(name)
            if text is None or name == OWN_FILE:
                continue
            for number, line in enumerate(text.splitlines(), 1):
                found += [f"{name}:{number}: {kind}: {hit}" for kind, hit in build_history(line) if (name, hit) not in ACCEPTED]
        self.assertEqual(found, [], HOW_TO_ACCEPT)

    def test_the_patterns_find_build_history_and_spare_other_names(self):
        history = [
            "b54", "see R392a", "(R12)", "R100", "WP-3b", "DM-15", "F21.15", "report a25", "under redesign",
            "raised from 200", "lowered from 9", "increased from 3", "decreased from 3", "bumped from 3", "renamed from old",
            "UN R155 is real but R156 alone is a row", "b85-small",
        ]  # fmt: skip
        spared = [
            "b429", "b5", "b64decode", "b64", "urlsafe_b64", "#b00", "color: #b00;", "R2", "R", "WP", "SPEC-12", "E164", "F21", "1.15",
            "reports", "raised to 200", "redesigned", "MATLAB R2024a", "R2024", "UN R155", "UN R157 (title) and R158", "UN R155 and UN R156",
            "UN R155 (cyber security management) and R156 (software updates), with ISO 24089",
        ]  # fmt: skip
        for text in history:
            with self.subTest(text):
                self.assertTrue(build_history(text))
        for text in spared:
            with self.subTest(text):
                self.assertEqual(build_history(text), [])

    def test_each_accepted_text_is_still_found(self):
        unused = []
        for name, text in ACCEPTED:
            held = tracked_text(name) if name in set(repo_files()) else None
            if held is not None and text not in held:
                unused.append(f"{name}: {text}")
        self.assertEqual(unused, [], "drop an accepted entry whose text is gone")
        self.assertTrue(all(ACCEPTED.values()), "an accepted text names its reason")


if __name__ == "__main__":
    unittest.main()
