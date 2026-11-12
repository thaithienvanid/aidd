"""A Spec's design files are `docs` entries of type `design-files`, and what Spec approval freezes is the same set of paths.

Invariant: for every Spec in the shape before (a `design.files` list beside `docs`), the paths it froze are all frozen in today's
shape, and no path more. A design file stays frozen whatever its entry says, so an entry that says `frozen: false` still freezes.
A base commit in the shape before decides a run as it did: its design files are read as today's, so an upgrade alone is no change
of an approved Spec, and a change to one of those files without a revision still stops. A head still in the shape before fails
with the step, because the head must be in today's shape."""

from __future__ import annotations

import itertools
import unittest

from helpers import git
from spec_repo_fixtures import PY, RepoCase, spec_text

from aidd import workitems
from aidd.kernel import documents, globs, retired_names
from aidd.testing import base_frozen, base_view
from aidd.workitems import spec_file

# Where each shape of a Spec lists the design files `design/*.md`.
BEFORE = 'design:\n  files: ["design/*.md"]\n'
TODAY = 'docs:\n  - type: design-files\n    path: "design/*.md"\n    frozen: true\n'


def froze_before(spec: dict) -> list[str]:
    """What Spec approval froze in the shape before: the test files, the design files, the frozen docs (frozen unless an entry says
    `frozen: false`), and the literal paths the test commands name."""
    design = list((spec.get("design") or {}).get("files", []))
    frozen = [d["path"] for d in spec.get("docs") or [] if d.get("frozen", True) is not False]
    return list(dict.fromkeys([*(spec.get("tests") or {}).get("files", []), *design, *frozen, *spec_file.command_path_literals(spec)]))


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


def old_spec(design: list | None, docs: list | None, tests: dict | None) -> dict:
    return {
        "type": "spec",
        "id": "SPEC-1",
        **({"design": {"files": design}} if design else {}),
        **({"docs": docs} if docs else {}),
        **({"tests": tests} if tests else {}),
    }


class TheFrozenSetIsTheSameSetOfPaths(unittest.TestCase):
    def table(self):
        for (d, design), (o, docs), (t, tests) in itertools.product(DESIGNS.items(), DOCS.items(), TESTS.items()):
            yield f"{d}; {o}; {t}", old_spec(design, docs, tests)

    def test_every_spec_in_the_shape_before_freezes_the_same_paths_once_it_reads_as_todays(self):
        cases = 0
        for name, raw in self.table():
            with self.subTest(name):
                cases += 1
                moved = workitems.todays_shape(raw)
                self.assertNotIn("design", moved)
                self.assertEqual(spec_file.frozen_paths(moved), froze_before(raw), "the same paths, in the same order")
                self.assertEqual(set(workitems.frozen_files(moved)), {p.partition("#")[0] for p in froze_before(raw)})
        self.assertEqual(cases, len(DESIGNS) * len(DOCS) * len(TESTS))

    def test_a_change_to_a_path_changes_what_a_spec_froze_exactly_where_it_did_before(self):
        """Raise-only: a path the shape before froze is frozen now (never fewer), and a path it left free is free (never more)."""
        for name, raw in self.table():
            moved = workitems.todays_shape(raw)
            before = [p for p in froze_before(raw) if "#" not in p]
            for path in CANDIDATES:
                if path == "pyproject.toml":
                    continue  # a manifest section is held by tests/test_base_frozen_sections.py
                with self.subTest(case=name, path=path):
                    got = workitems.frozen_change(moved, path, lambda _: ("before", "after"))
                    self.assertEqual(got, globs.match_any(before, path))

    def test_a_design_file_is_frozen_whatever_its_entry_says(self):
        for frozen in (True, False, None):
            spec = {"type": "spec", "id": "SPEC-1", "docs": [entry("d/**", "design-files", frozen)]}
            with self.subTest(frozen=frozen):
                self.assertEqual(spec_file.frozen_paths(spec), ["d/**"])
                self.assertEqual(workitems.design_paths(spec), ["d/**"])
                self.assertTrue(workitems.frozen_change(spec, "d/a.md", lambda _: ("a", "b")))

    def test_a_design_that_would_lose_a_path_is_refused_not_dropped(self):
        for name, design in {
            "more than files": {"files": ["d/a.md"], "note": "x"},
            "no files": {"files": []},
            "a path that is no string": {"files": [3]},
            "not a mapping": "d/a.md",
        }.items():
            with self.subTest(name), self.assertRaises(retired_names.Refused):
                workitems.todays_shape({"type": "spec", "id": "SPEC-1", "design": design})


class TheBaseCommitInTheShapeBefore(RepoCase):
    """An approved Spec on the base lists its design files as `design.files`; the head holds them as `docs` entries."""

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
        before = workitems.todays_shape(documents.split_front_matter(git(self.root, "show", "main:specs/SPEC-1.md"), "specs/SPEC-1.md")[0])
        _, notes = base_view.spec_view(held["SPEC-1"], before)
        return [problem, *[n for n in notes if "frozen files" in n]]

    def test_an_upgrade_alone_is_no_change_of_what_the_approved_spec_froze(self):
        text = self.landed(BEFORE)
        self.assertEqual(self.change(text, TODAY, {}), [""])

    def test_a_change_to_a_design_file_still_stops_whichever_shape_the_head_is_in(self):
        text = self.landed(BEFORE)
        [problem] = self.change(text, TODAY, {"design/flow.md": "# a new flow\n"})
        self.assertIn("design/flow.md", problem)
        self.assertIn("SPEC-1", problem)
        self.assertIn("spec.revise", problem)

    def test_a_head_that_drops_a_design_file_from_its_spec_says_so_and_the_base_still_holds_it(self):
        text = self.landed(BEFORE)
        found = self.change(text, "", {})
        self.assertEqual(len(found), 2, found)
        self.assertEqual(found[0], "", "the file itself is unchanged")
        self.assertIn("frozen files", found[1])
        [problem] = self.change(text, "", {"design/flow.md": "# a new flow\n"})[:1]
        self.assertIn("design/flow.md", problem, "dropping the entry freezes nothing for the head: the base's Spec decides")

    def test_a_head_still_in_the_shape_before_fails_with_the_step(self):
        text = self.landed(TODAY)
        self.put(self.root, "specs/SPEC-1.md", text.replace("tests:\n", BEFORE + "tests:\n", 1))
        self.commit(self.root, "change")
        with self.assertRaises(documents.DocumentError) as caught:
            self.run_aidd(require_green=True, red=False)
        self.assertIn("aidd upgrade --yes", str(caught.exception))
