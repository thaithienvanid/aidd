"""A frozen manifest section (`pyproject.toml#tool.pytest`) freezes its value, never its manifest's bytes, in both checks that read it:
the test run's rule for a change that does not revise the Spec (`testing.base_frozen_problem`) and the held Spec's own check against
its approval (`delegation.local_run.frozen_problem`). Invariant: only an input whose frozen section holds the same value on both sides
passes where the whole file used to stop; a section changed or removed, a manifest gone, renamed, or unreadable, and a whole-file
entry of the same manifest still stop. `aidd new spec` writes these entries into every Spec, so a dependency bump must pass.
"""

from __future__ import annotations

import unittest

from helpers import git
from spec_repo_fixtures import RepoCase, spec_text
from test_base_frozen import frozen

from aidd import workitems
from aidd.delegation import local_run


PYPROJECT = '[project]\nname = "x"\ndependencies = ["a==1"]\n\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
PACKAGE = '{"name": "x", "dependencies": {"a": "1.0.0"}, "scripts": {"test": "vitest", "lint": "eslint ."}}\n'


class FrozenSections(RepoCase):
    """A frozen manifest section freezes its value, not the manifest: a dependency bump beside it passes, and any change to the
    section, or a manifest that is gone or cannot be read, counts. A whole-file entry of the same manifest wins."""

    SECTIONS = ("tests/test_shared.py", "pyproject.toml#tool.pytest", "package.json#scripts.test")
    TABLE = {  # name: (the files the head writes, None removes one; the Spec freezes the whole pyproject too; frozen)
        "a dependency bump in pyproject.toml": ({"pyproject.toml": PYPROJECT.replace("a==1", "a==2")}, False, False),
        "a dependency bump in package.json": ({"package.json": PACKAGE.replace("1.0.0", "2.0.0")}, False, False),
        "another script than the test's": ({"package.json": PACKAGE.replace("eslint .", "eslint src")}, False, False),
        "the frozen pytest section changed": ({"pyproject.toml": PYPROJECT.replace('["tests"]', '["other"]')}, False, True),
        "the frozen pytest section removed": ({"pyproject.toml": PYPROJECT.split("\n\n")[0] + "\n"}, False, True),
        "the test script changed": ({"package.json": PACKAGE.replace('"vitest"', '"vitest --passWithNoTests"')}, False, True),
        "the manifest removed": ({"pyproject.toml": None}, False, True),
        "the manifest renamed": ({"pyproject.toml": None, "pyproject2.toml": PYPROJECT}, False, True),
        "the manifest unreadable at the head": ({"pyproject.toml": PYPROJECT + "[[[\n"}, False, True),
        "a dependency bump, the whole file frozen too": ({"pyproject.toml": PYPROJECT.replace("a==1", "a==2")}, True, True),
    }

    def landed(self, whole: bool) -> tuple[str, dict]:
        self.put(self.root, "pyproject.toml", PYPROJECT)
        self.put(self.root, "package.json", PACKAGE)
        self.put(self.root, "tests/test_shared.py", "def test_a():\n    assert True\n")
        text = spec_text("SPEC-1", status="approved", files=(*self.SECTIONS, *(["pyproject.toml"] if whole else [])))
        self.put(self.root, "specs/SPEC-1.md", text)
        self.commit(self.root, "SPEC-1 approved")
        return git(self.root, "rev-parse", "HEAD"), workitems.load_object(text, "specs/SPEC-1.md")[0]

    def changed(self, files: dict[str, str | None]) -> list[str]:
        for path, body in files.items():
            if body is None:
                (self.root / path).unlink()
            else:
                self.put(self.root, path, body)
        self.commit(self.root, "change")
        return list(files)

    def test_the_test_run_and_the_delegates_own_check_read_a_section_by_its_value(self):
        bases = {}
        for whole in (False, True):
            git(self.root, "switch", "-qfC", f"base-{whole}", "main")
            bases[whole] = self.landed(whole)
        for name, (files, whole, expected) in self.TABLE.items():
            with self.subTest(name):
                base, spec = bases[whole]
                git(self.root, "switch", "-qfC", "case", base)
                paths = self.changed(files)
                self.assertEqual(bool(frozen(self.root, "specs", base, paths)), expected, "a change that does not hold the Spec")
                head = git(self.root, "rev-parse", "HEAD")
                own = local_run.frozen_problem(str(self.root), head, "specs", ("specs/SPEC-1.md", spec), base)
                self.assertEqual(bool(own), expected, f"the held Spec's own check against its approval: {own}")


if __name__ == "__main__":
    unittest.main()
