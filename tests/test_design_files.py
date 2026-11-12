"""A Spec's design files are `docs` entries of type `design-files`, and what Spec approval freezes is the set of paths the table below
says: the test files, the design files, the frozen docs (frozen unless an entry says `frozen: false`), and the literal paths the test
commands name.

Invariant: for every combination of design files, docs, and tests, the paths a Spec freezes are exactly those, in that order, and a
change to a path is a change of what the Spec froze exactly where it is one of them. A design file stays frozen whatever its entry
says, so an entry that says `frozen: false` still freezes. A change to a design file of an approved Spec on the base without a
revision stops a run, and a head that drops a design file from its Spec says so while the base's Spec still decides."""

from __future__ import annotations

import itertools
import unittest

from helpers import git
from spec_repo_fixtures import PY, RepoCase, spec_text

from aidd import workitems
from aidd.kernel import documents, globs
from aidd.testing import base_frozen, base_view
from aidd.workitems import spec_file

# How a Spec lists the design files `design/*.md`.
TODAY = 'docs:\n  - type: design-files\n    path: "design/*.md"\n    frozen: true\n'


def should_freeze(design: list | None, docs: list | None, spec: dict) -> list[str]:
    """What Spec approval freezes: the test files, the design files, the frozen docs (frozen unless an entry says `frozen: false`), and
    the literal paths the test commands name, each path once."""
    frozen = [d["path"] for d in docs or [] if d.get("frozen", True) is not False]
    return list(dict.fromkeys([*(spec.get("tests") or {}).get("files", []), *(design or []), *frozen, *spec_file.command_path_literals(spec)]))


def entry(path: str, kind: str = "tech-spec", frozen: bool | None = None) -> dict:
    return {"type": kind, "path": path, **({} if frozen is None else {"frozen": frozen})}


# Each field of a Spec that names what approval freezes, with every value the cases below combine: none, one, a glob, many, a
# repeated path, and a path another entry names too.
DESIGNS = {
    "none": None,
    "a file": ["d/a.md"],
    "a glob": ["d/**"],
    "several, one twice": ["d/a.md", "d/**", "d/a.md"],
}
DOCS = {
    "none": None,
    "a frozen doc": [entry("x/tech.md")],
    "a living doc": [entry("x/runbook.md", "runbook", False)],
    "a frozen doc on a design path": [entry("d/a.md", "other")],
    "a living doc on a design path": [entry("d/a.md", "other", False)],
    "a living doc on a design glob": [entry("d/**", "other", False)],
    "a frozen doc after a living one": [entry("x/r.md", "runbook", False), entry("x/tech.md")],
}
TESTS = {
    "no test files": None,
    "a test file": {"files": ["t/test_a.py"]},
    "a manifest section": {"files": ["pyproject.toml#tool.pytest"]},
    "a command that names a path": {"files": ["t/test_a.py"], "commands": [{"name": "c", "command": [PY, "tools/check.py"], "new_behavior": True}]},
}
# Paths a change may touch: each frozen path, a path inside each glob, a path in none, and a path beside one.
CANDIDATES = ["d/a.md", "d/b.md", "d/deep/c.md", "x/tech.md", "x/runbook.md", "t/test_a.py", "tools/check.py", "pyproject.toml", "src/app.py", "d.md"]


def spec_of(design: list | None, docs: list | None, tests: dict | None) -> dict:
    """A Spec that lists `design` as `design-files` entries after the `docs` it holds."""
    entries = [*(docs or []), *({"type": "design-files", "path": path, "frozen": True} for path in dict.fromkeys(design or []))]
    return {"type": "spec", "id": "SPEC-1", **({"docs": entries} if entries else {}), **({"tests": tests} if tests else {})}


class TheFrozenSetIsTheSetTheTableSays(unittest.TestCase):
    def table(self):
        for (d, design), (o, docs), (t, tests) in itertools.product(DESIGNS.items(), DOCS.items(), TESTS.items()):
            spec = spec_of(design, docs, tests)
            yield f"{d}; {o}; {t}", spec, should_freeze(design, docs, spec)

    def test_every_spec_freezes_the_paths_the_table_says_in_its_order(self):
        cases = 0
        for name, spec, want in self.table():
            with self.subTest(name):
                cases += 1
                self.assertEqual(spec_file.frozen_paths(spec), want, "the same paths, in the same order")
                self.assertEqual(set(workitems.frozen_files(spec)), {p.partition("#")[0] for p in want})
        self.assertEqual(cases, len(DESIGNS) * len(DOCS) * len(TESTS))

    def test_a_change_to_a_path_changes_what_a_spec_froze_exactly_where_the_table_says(self):
        """A path the table freezes is frozen (never fewer), and a path it leaves free is free (never more)."""
        for name, spec, want in self.table():
            frozen = [p for p in want if "#" not in p]
            for path in CANDIDATES:
                if path == "pyproject.toml":
                    continue  # a manifest section is held by tests/test_base_frozen_sections.py
                with self.subTest(case=name, path=path):
                    got = workitems.frozen_change(spec, path, lambda _: ("before", "after"))
                    self.assertEqual(got, globs.match_any(frozen, path))

    def test_a_design_file_is_frozen_whatever_its_entry_says(self):
        for frozen in (True, False, None):
            spec = {"type": "spec", "id": "SPEC-1", "docs": [entry("d/**", "design-files", frozen)]}
            with self.subTest(frozen=frozen):
                self.assertEqual(spec_file.frozen_paths(spec), ["d/**"])
                self.assertEqual(workitems.design_paths(spec), ["d/**"])
                self.assertTrue(workitems.frozen_change(spec, "d/a.md", lambda _: ("a", "b")))


class TheBaseCommitHoldsTheDesignFiles(RepoCase):
    """An approved Spec on the base lists its design files as `docs` entries; the head is compared with it."""

    FILES = {"design/flow.md": "# the approved flow\n", "tools/verify.py": "raise SystemExit(0)\n"}

    def landed(self, base_shape: str) -> str:
        for path, body in self.FILES.items():
            self.put(self.root, path, body)
        text = spec_text("SPEC-1", status="approved", files=("tools/verify.py",))
        self.put(self.root, "specs/SPEC-1.md", text.replace("tests:\n", base_shape + "tests:\n", 1))
        self.commit(self.root, "SPEC-1 approved")
        self.branch()
        return text

    def change(self, text: str, head_shape: str, files: dict[str, str]) -> list[str]:
        """Commit the Spec in `head_shape` and `files`, and return the problems `base_frozen_problem` and `spec_view` find."""
        base = git(self.root, "rev-parse", "main")
        self.put(self.root, "specs/SPEC-1.md", text.replace("tests:\n", head_shape + "tests:\n", 1))
        for path, body in files.items():
            self.put(self.root, path, body)
        self.commit(self.root, "change")
        paths = git(self.root, "diff", "--name-only", "--no-renames", base, "HEAD").split()
        held = {"SPEC-1": workitems.load_object(git(self.root, "show", "HEAD:specs/SPEC-1.md"), "specs/SPEC-1.md")[0]}
        problem, _, _ = base_frozen.base_frozen_problem(str(self.root), "specs", (base, git(self.root, "rev-parse", "HEAD")), paths, held)
        before = documents.split_front_matter(git(self.root, "show", "main:specs/SPEC-1.md"), "specs/SPEC-1.md")[0]
        _, notes = base_view.spec_view(held["SPEC-1"], before)
        return [problem, *[n for n in notes if "frozen files" in n]]

    def test_a_head_that_changes_nothing_is_no_change_of_what_the_approved_spec_froze(self):
        text = self.landed(TODAY)
        self.assertEqual(self.change(text, TODAY, {}), [""])

    def test_a_change_to_a_design_file_stops_a_run(self):
        text = self.landed(TODAY)
        [problem] = self.change(text, TODAY, {"design/flow.md": "# a new flow\n"})
        self.assertIn("design/flow.md", problem)
        self.assertIn("SPEC-1", problem)
        self.assertIn("spec.revise", problem)

    def test_a_head_that_drops_a_design_file_from_its_spec_says_so_and_the_base_still_holds_it(self):
        text = self.landed(TODAY)
        found = self.change(text, "", {})
        self.assertEqual(len(found), 2, found)
        self.assertEqual(found[0], "", "the file itself is unchanged")
        self.assertIn("frozen files", found[1])
        [problem] = self.change(text, "", {"design/flow.md": "# a new flow\n"})[:1]
        self.assertIn("design/flow.md", problem, "dropping the entry freezes nothing for the head: the base's Spec decides")

    def test_a_head_that_holds_a_key_this_aidd_does_not_read_stops_a_run_and_names_it(self):
        text = self.landed(TODAY)
        self.put(self.root, "specs/SPEC-1.md", text.replace("tests:\n", 'design:\n  files: ["design/*.md"]\ntests:\n', 1))
        self.commit(self.root, "change")
        with self.assertRaises(documents.DocumentError) as caught:
            self.run_aidd(require_green=True, red=False)
        self.assertIn("design", str(caught.exception))
