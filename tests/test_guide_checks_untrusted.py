"""The guide and the manifests it is checked against are untrusted repository text (tests/test_untrusted_input.py holds the rules):
no pattern may take long on a hostile file, every read is capped through the safe reader, and a path from the guide is probed
only when it stays inside the repository with no link on the way. A file or a path this cannot judge gives no warning."""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401  # the hermetic environment
from helpers import git

from aidd.workitems import guide_checks

PATH, COMMAND = guide_checks.PATH_MISSING, guide_checks.COMMAND_MISSING
SECONDS = 1.0

# (name, a Makefile, the targets it names, or None when this cannot tell)
MAKEFILES = [
    ("a plain target", "test:\n\tpytest\n", {"test"}),
    ("a target with prerequisites", "build: deps gen\n\tgo build\n", {"build"}),
    ("two names in one rule", "lint build: deps\n\ttrue\n", {"lint", "build"}),
    ("a double-colon rule", "docs:: a\n\ttrue\n", {"docs"}),
    ("a simple assignment", "CC := gcc\nOUT = a:b\ntest:\n\ttrue\n", {"test"}),
    ("a double-colon assignment", "CC ::= gcc\ntest:\n\ttrue\n", {"test"}),
    ("a target-specific variable", "test: CFLAGS=-O2\n\ttrue\n", {"test"}),
    ("a pattern rule", "%.o: %.c\n\tcc\nall:\n\ttrue\n", {"all"}),
    ("the catch-all pattern", "%: x\n\ttrue\n", None),
    ("an include", "include rules.mk\ntest:\n\ttrue\n", None),
    ("a dash include", "-include rules.mk\ntest:\n\ttrue\n", None),
    ("a target named like an include", "included:\n\ttrue\n", {"included"}),
    ("a variable in a target name", "$(NAME):\n\ttrue\n", None),
    ("a comment, a recipe, and a special target", "# a: b\n.PHONY: test\ntest:\n\techo a: b\n", {"test"}),
    ("a conditional", "ifeq ($(OS),Linux)\ntest:\n\ttrue\nendif\n", {"test"}),
    ("CRLF", "test:\r\n\ttrue\r\n", {"test"}),
    ("no target", "", set()),
]


def seconds(call, *args) -> float:
    start = time.perf_counter()
    call(*args)
    return time.perf_counter() - start


class Asked:
    """Records each path `os.path.lexists` is asked about, and answers as it would."""

    def __init__(self) -> None:
        self.paths: list[str] = []
        self.real = os.path.lexists

    def __call__(self, path) -> bool:
        self.paths.append(str(path))
        return self.real(path)


class MakefileShapes(unittest.TestCase):
    def test_each_shape_gives_its_answer(self):
        for name, text, expected in MAKEFILES:
            with self.subTest(name):
                self.assertEqual(guide_checks.make_targets_of(text), expected)

    def test_a_hostile_makefile_is_read_in_well_under_a_second(self):
        spaces = " " * 1_000_000
        hostile = {
            "one line of spaces": spaces + "\n",
            "many lines of spaces and no colon": (" x" * 40 + "\n") * 20_000,
            "many long lines of words and no colon": ("a " * 900 + "\n") * 500,
            "one line of colons": ":" * 1_000_000 + "\n",
            "a long line with the colon last": "a" + " " * 100_000 + ":",
            "many targets": "".join(f"t{n}: x\n" for n in range(100_000)),
        }
        for name, text in hostile.items():
            with self.subTest(name):
                self.assertLess(seconds(guide_checks.make_targets_of, text), SECONDS)


class HostileGuides(unittest.TestCase):
    def check(self, guide: str, files: dict[str, str] | None = None) -> tuple[float, list[tuple[str, str]]]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel, text in {"AGENTS.md": guide, **(files or {})}.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(text, encoding="utf-8")
            start = time.perf_counter()
            found = guide_checks.guide_findings(root)
            return time.perf_counter() - start, found

    def test_a_hostile_guide_is_read_in_well_under_a_second(self):
        hostile = {
            "one line of spaces": " " * 1_000_000,
            "many lines of spaces": " x" * 20 + ("\n" + " " * 500) * 2000,
            "many openers of aidd's section and no end": "<!-- aidd -->\n" * 70_000,
            "many comment openers and no end": "<!--\n" * 200_000,
            "many open brackets": ("[" * 1900 + "\n") * 500,
            "many link starts": ("](" * 600 + "\n") * 500,
            "many backticks": ("`" * 1900 + "\n") * 500,
            "one backtick and a long line": "`" + "a" * 1_000_000,
            "long commands": "`" + "make " + "a " * 1000 + "`\n" + ("`make " + "&& " * 100 + "`\n") * 2000,
            "a long code block": "```\n" + ("make a && " * 150 + "\n") * 2000,
        }
        for name, text in hostile.items():
            with self.subTest(name):
                took, found = self.check(text, {"Makefile": "test:\n\ttrue\n"})
                self.assertLess(took, SECONDS)
                self.assertEqual(found, [], "a line that is no sentence, target, or command names nothing")

    def test_a_manifest_past_its_cap_or_deeper_than_json_allows_says_nothing(self):
        big = '{"scripts": {"build": "' + "x" * (guide_checks.MAX_MANIFEST_BYTES + 1) + '"}}'
        deep = "[" * 100_000
        for name, text in {"too large": big, "too deep": deep, "not JSON": "{", "not an object": "[1]"}.items():
            with self.subTest(name):
                took, found = self.check("Run `npm run deploy`.", {"package.json": text})
                self.assertLess(took, SECONDS)
                self.assertEqual(found, [])

    def test_a_makefile_past_its_cap_says_nothing(self):
        big = "test:\n\ttrue\n" + "# " + "x" * guide_checks.MAX_MANIFEST_BYTES + "\n"
        self.assertEqual(self.check("Run `make deploy`.", {"Makefile": big})[1], [])


class PathsThatStayInside(unittest.TestCase):
    """A path from the guide is joined to the repository only when it stays inside, with no link on the way."""

    def build(self, root: Path, outside: Path) -> None:
        git(root, "init", "-q")
        (root / "src").mkdir()
        (root / "src" / "app.py").write_text("", encoding="utf-8")
        (outside / "secret").write_text("", encoding="utf-8")
        (root / "linked").symlink_to(outside)
        (root / "file-link").symlink_to(outside / "secret")

    # (name, the guide, the codes it gives)
    CASES = [
        ("a path inside that exists", "See `src/app.py`.", []),
        ("a path inside that is missing", "See `src/old.py`.", [PATH]),
        ("a link inside that exists", "See [app](src/app.py).", []),
        ("a link inside that is missing", "See [app](src/old.py).", [PATH]),
        ("a path up out of the repository", "See `src/../../secret`.", []),
        ("a path that starts with two dots", "See `../secret/x`.", []),
        ("a link up out of the repository", "See [x](../../secret).", []),
        ("a link that goes up and down", "See [x](src/../../secret).", []),
        ("an absolute path", "See `/etc/passwd/x`.", []),
        ("an absolute link", "See [x](/etc/passwd).", []),
        ("a path through a link to a folder", "See `linked/secret`.", []),
        ("a link through a link to a folder", "See [x](linked/secret).", []),
        ("a path that is a link to a file", "See `file-link/x`.", []),
        ("a path with a NUL", "See `src/app\0.py`.", []),
        ("a link with a NUL", "See [x](src/app\0.py).", []),
        ("a path with a backslash", "See `src\\app.py`.", []),
        ("a link with a backslash", "See [x](src\\old.py).", []),
        ("a URL", "See `https://example.com/src/old.py` and [x](https://example.com/old).", []),
        ("an anchor only", "See [x](#top).", []),
        ("a glob", "See `src/*.py` and [x](src/*.py).", []),
        ("a command that is a path through a link", "Run `./linked/run.sh`.", []),
        ("a command that is a path up out", "Run `./src/../../run.sh`.", []),
    ]

    def test_a_path_that_leaves_the_repository_is_never_probed_and_gives_no_warning(self):
        for name, guide, codes in self.CASES:
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as away:
                root, outside = Path(tmp).resolve(), Path(away).resolve()
                self.build(root, outside)
                (root / "AGENTS.md").write_text(guide, encoding="utf-8")
                asked = Asked()
                with mock.patch("os.path.lexists", asked):
                    found = guide_checks.guide_findings(root)
                self.assertEqual([code for code, _ in found], codes, found)
                for path in asked.paths:
                    self.assertTrue(path.startswith(str(root) + "/") and "/../" not in path and "\0" not in path, f"probed {path!r}")
                    self.assertFalse(path.startswith(str(outside)), f"probed {path!r}")
                if not codes:
                    self.assertFalse([p for p in asked.paths if "secret" in p or "passwd" in p or "run.sh" in p], f"probed {asked.paths}")


if __name__ == "__main__":
    unittest.main()
