"""Control tests for which Specs' own tests `aidd test` runs.

Invariant: every Spec that applies to a change has its commands run, for zero, one, or many Specs, and none is skipped
silently. A Spec applies when the diff holds it (added, changed, deleted, or moved), the branch is `spec/<ID>`, or `--spec`
names it. A Spec the diff only reaches by a Task's scope gets a note and no run, so an unrelated change never fails on tests
that fail by design until the Spec is built.
"""

from __future__ import annotations

import os
import unittest

from helpers import git
from spec_repo_fixtures import FAIL, PASS, RepoCase, spec_text

from aidd import testing
from aidd.kernel.documents import DocumentError
from aidd.testing import governing


class GoverningSpecsTests(RepoCase):
    """Every Spec that governs the change has its commands run: the Specs the diff holds (zero to three), the Spec a
    branch is named for, and an approved Spec whose Task scope the diff touches."""

    def specs_branch(self, n: int, statuses: str = "draft") -> None:
        self.branch()
        for i in range(1, n + 1):
            self.put(self.root, f"specs/SPEC-{i}.md", spec_text(f"SPEC-{i}", status=statuses, code=FAIL if i == 2 else PASS))
        self.put(self.root, "app/x.py", "x = 1\n")
        self.commit(self.root, "specs and code")

    def test_the_commands_of_every_changed_spec_run_for_zero_to_three(self):
        cases = [
            # (Specs on the branch, --spec, commands that run, exit)
            (0, None, {"unit"}, 0),
            (1, None, {"unit", "check"}, 0),
            (2, None, {"unit", "SPEC-1.check", "SPEC-2.check"}, 1),
            (3, None, {"unit", "SPEC-1.check", "SPEC-2.check", "SPEC-3.check"}, 1),
            # `--spec` adds a Spec to the run and hides none that applies
            (1, "specs/SPEC-1.md", {"unit", "check"}, 0),
            (2, "specs/SPEC-1.md", {"unit", "SPEC-1.check", "SPEC-2.check"}, 1),
            (3, "specs/SPEC-2.md", {"unit", "SPEC-1.check", "SPEC-2.check", "SPEC-3.check"}, 1),
        ]
        for n, given, expected, code in cases:
            with self.subTest(specs=n, spec=given):
                self.fresh()
                self.specs_branch(n)
                evidence, _ = self.run_aidd(spec=given)
                self.assertEqual({name for name, _ in self.ran(evidence)}, expected)
                self.assertEqual(testing.exit_code(evidence), code)

    def test_a_flag_never_hides_a_spec_that_applies(self):
        """`--spec` names a Spec to run, even one the change does not reach. Every Spec that applies still runs: the head's
        and the base's, a changed one and one reached by scope, a deleted one too."""
        spec = "specs/SPEC-1.md"
        cases = [
            # (Specs at the base, what the head does to SPEC-1, --spec, what ran, exit)
            ({"SPEC-1": "approved"}, "delete", "specs/SPEC-2.md", {"unit", "SPEC-1.check", "SPEC-2.check"}, 1),  # the head deleted SPEC-1
            ({"SPEC-1": "approved"}, "keep", "specs/SPEC-2.md", {"unit", "check"}, 0),  # SPEC-1 is reached by scope only: a note, no run
            ({"SPEC-1": "approved"}, "keep", "specs/SPEC-1.md", {"unit", "check"}, 1),  # the flag names SPEC-1, so it runs
            ({"SPEC-1": "approved"}, "keep", None, {"unit"}, 0),
            ({"SPEC-1": "draft"}, "delete", "specs/SPEC-2.md", {"unit", "check"}, 0),  # a draft never applied, so the flag adds only SPEC-2
        ]
        for base, act, given, expected, code in cases:
            with self.subTest(base=base, head=act, spec=given):
                self.fresh()
                for sid, status in base.items():
                    self.put(self.root, f"specs/{sid}.md", spec_text(sid, status=status, code=FAIL))
                self.put(self.root, "specs/SPEC-2.md", spec_text("SPEC-2", status="draft", scope="lib/"))
                self.commit(self.root, "the Specs landed")
                self.branch()
                if act == "delete":
                    (self.root / spec).unlink()
                self.put(self.root, "app/x.py", "x = 1\n")
                self.commit(self.root, "the head's change")
                evidence, _ = self.run_aidd(spec=given)
                self.assertEqual({name for name, _ in self.ran(evidence)}, expected)
                self.assertEqual(testing.exit_code(evidence), code)

    def test_an_approved_spec_that_landed_earlier_runs_when_the_change_holds_it_and_is_noted_when_it_only_touches_its_scope(self):
        """The implementation PR holds no Spec: the Spec is on `main` already. On a branch named for it, or with `--spec`, its
        commands run green, and red on the base while it is not built. On any other branch the change only touches its scope, so
        the verdict is the suite's, the Spec is noted, and the evidence lists it."""
        made = "import os, sys; sys.exit(0 if os.path.exists('app/greet.py') else 1)"
        both = {("unit", "green"), ("check", "green"), ("check", "red")}
        cases = [
            # (status, a path the change touches, branch, --spec, what ran, noted as not run)
            ("approved", "app/greet.py", "feat", None, {("unit", "green")}, True),
            ("in_progress", "app/greet.py", "feat", None, {("unit", "green")}, True),
            ("approved", "app/greet.py", "spec/SPEC-1", None, both, False),
            ("approved", "app/greet.py", "feat", "specs/SPEC-1.md", both, False),
            ("in_review", "app/greet.py", "feat", None, {("unit", "green")}, False),  # built: its stored status lags after a merge
            ("approved", "docs/guide.md", "feat", None, {("unit", "green")}, False),  # outside every Task scope
        ]
        for status, touched, branch, given, expected, noted in cases:
            with self.subTest(status=status, touched=touched, branch=branch, spec=given):
                self.fresh()
                self.put(self.root, "specs/SPEC-1.md", spec_text("SPEC-1", status=status, code=made, new_behavior=True))
                self.commit(self.root, "the Spec landed")
                self.branch(branch)
                self.put(self.root, touched, "def greet():\n    return 'hello'\n")
                self.commit(self.root, "implement")
                evidence, notes = self.run_aidd(spec=given)
                self.assertEqual(self.ran(evidence), expected)
                self.assertEqual(testing.exit_code(evidence), 0)
                self.assertEqual(evidence["specs_not_run"], ["specs/SPEC-1.md"] if noted else [])
                self.assertEqual(any("did not run" in n and "spec/SPEC-1" in n for n in notes), noted, notes)

    def test_only_an_open_spec_is_reached_by_its_scope_and_none_of_them_runs(self):
        statuses = ["draft", "ready", "approved", "in_progress", "in_review", "done", "rolled_back", "cancelled"]
        for i, status in enumerate(statuses, 1):
            self.put(self.root, f"specs/SPEC-{i}.md", spec_text(f"SPEC-{i}", status=status))
        self.commit(self.root, "Specs in every status landed")
        self.branch()
        self.put(self.root, "app/x.py", "x = 1\n")
        self.commit(self.root, "code in every scope")
        files = [{"path": "app/x.py"}]
        head = git(self.root, "rev-parse", "HEAD")
        found, _ = governing.find_governing(str(self.root), "specs", head, governing.GoverningChange(files, ["app/x.py"], "feat"))
        self.assertEqual({(g.data["status"], g.why, g.runs) for g in found}, {("approved", "scope", False), ("in_progress", "scope", False)})
        found, _ = governing.find_governing(str(self.root), "specs", head, governing.GoverningChange(files, ["docs/x.md"], "feat"))
        self.assertEqual(found, [], "a path outside every scope reaches no Spec")

    def test_a_prose_fix_to_a_built_spec_runs_green_only_and_a_new_spec_runs_red(self):
        """Red on the base proves new behavior, so it runs for a Spec the base does not hold as built, and never for a built one
        the base already satisfies."""
        made = "import os, sys; sys.exit(0 if os.path.exists('app/greet.py') else 1)"
        both = {("unit", "green"), ("check", "green"), ("check", "red")}
        cases = [
            # (the Spec at the base, or None when it is new; whether the base has the code; whether the change adds the code; ran)
            (None, False, True, both),
            ("approved", False, True, both),
            ("in_progress", False, True, both),
            ("done", True, False, {("unit", "green"), ("check", "green")}),  # a prose fix to a built Spec
            ("in_review", True, False, {("unit", "green"), ("check", "green")}),
        ]
        for status, base_code, adds_code, expected in cases:
            with self.subTest(status=status):
                self.fresh()
                if base_code:
                    self.put(self.root, "app/greet.py", "def greet():\n    return 'hello'\n")
                if status:
                    self.put(self.root, "specs/SPEC-1.md", spec_text("SPEC-1", status=status, code=made, new_behavior=True))
                self.commit(self.root, "base")
                self.branch()
                if adds_code:
                    self.put(self.root, "app/greet.py", "def greet():\n    return 'hello'\n")
                path = self.root / "specs/SPEC-1.md"
                path.parent.mkdir(exist_ok=True)
                path.write_text(
                    (path.read_text(encoding="utf-8") if status else spec_text("SPEC-1", status="in_review", code=made, new_behavior=True)) + "\nA sentence.\n",
                    encoding="utf-8",
                )
                self.commit(self.root, "the change")
                evidence, _ = self.run_aidd()
                self.assertEqual(self.ran(evidence), expected)
                self.assertEqual(testing.exit_code(evidence), 0)

    def test_a_spec_that_governs_at_the_base_still_governs_when_the_head_deletes_moves_or_lowers_it(self):
        """The head is the author's: deleting, moving, breaking, renaming, or lowering the Spec file must not drop its tests."""
        spec = "specs/SPEC-1.md"

        def delete(root):
            (root / spec).unlink()

        def move_out(root):
            (root / "docs").mkdir(exist_ok=True)
            (root / spec).rename(root / "docs/SPEC-1.md")

        def break_front_matter(root):
            (root / spec).write_text("no front matter any more\n", encoding="utf-8")

        def rename_inside(root):
            (root / spec).rename(root / "specs/SPEC-1-renamed.md")

        def lower(root):
            path = root / spec
            path.write_text(path.read_text(encoding="utf-8").replace("status: approved", "status: done"), encoding="utf-8")

        def change_id(root):
            path = root / spec
            path.write_text(path.read_text(encoding="utf-8").replace("id: SPEC-1", "id: SPEC-7"), encoding="utf-8")

        def keep(root):
            pass

        cases = [
            # (the Spec at the base, what the head does to it, ran, exit)
            ("approved", delete, {("unit", "green"), ("check", "green")}, 1),
            ("approved", move_out, {("unit", "green"), ("check", "green")}, 1),
            ("approved", break_front_matter, {("unit", "green"), ("check", "green")}, 1),
            ("approved", change_id, {("unit", "green"), ("SPEC-1.check", "green"), ("SPEC-7.check", "green")}, 1),  # SPEC-1 is gone under that id
            ("approved", rename_inside, {("unit", "green"), ("check", "green")}, 1),  # the head still holds it, as a changed Spec
            ("approved", lower, {("unit", "green"), ("check", "green")}, 1),
            ("approved", keep, {("unit", "green")}, 0),  # the head leaves the Spec alone: only its scope is reached, so a note
            ("in_progress", delete, {("unit", "green"), ("check", "green")}, 1),
            # a Spec that did not govern at the base is no one's to keep
            ("draft", delete, {("unit", "green")}, 0),
            ("ready", delete, {("unit", "green")}, 0),
            ("done", delete, {("unit", "green")}, 0),
            ("cancelled", move_out, {("unit", "green")}, 0),
        ]
        for status, act, ran, code in cases:
            with self.subTest(status=status, head=act.__name__):
                self.fresh()
                self.put(self.root, spec, spec_text("SPEC-1", status=status, code=FAIL))
                self.commit(self.root, "the Spec landed")
                self.branch()
                act(self.root)
                self.put(self.root, "app/x.py", "x = 1\n")
                self.commit(self.root, "the head's change")
                evidence, notes = self.run_aidd()
                self.assertEqual((self.ran(evidence), testing.exit_code(evidence)), (ran, code))
                if act is delete and code == 1:
                    self.assertTrue(any("SPEC-1" in n and "spec" in n.lower() for n in notes), notes)

    def test_a_spec_branch_runs_its_spec_whatever_the_diff_touches(self):
        self.put(self.root, "specs/SPEC-5.md", spec_text("SPEC-5", status="ready", scope="lib/", code=FAIL))
        self.commit(self.root, "the Spec landed")
        self.branch("spec/SPEC-5")
        self.put(self.root, "docs/guide.md", "guide\n")
        self.commit(self.root, "docs")
        evidence, _ = self.run_aidd()
        self.assertEqual((self.ran(evidence), testing.exit_code(evidence)), ({("unit", "green"), ("check", "green")}, 1))

    def test_ci_checks_out_a_commit_so_the_branch_comes_from_the_platform_and_every_decider_reads_it_alike(self):
        """The `spec/<ID>` rule is one rule: a local run reads the checked-out branch, CI reads the name its platform gives a pull or
        merge request, and a run in either place finds the same Spec."""
        from unittest import mock

        self.put(self.root, "specs/SPEC-5.md", spec_text("SPEC-5", status="ready", scope="lib/", code=FAIL))
        self.commit(self.root, "the Spec landed")
        self.branch("spec/SPEC-5")
        self.put(self.root, "docs/guide.md", "guide\n")
        self.commit(self.root, "docs")
        local, _ = self.run_aidd()
        git(self.root, "checkout", "-q", "--detach")
        cases = [
            # (the platform's variable, what it names, whether the Spec is found)
            ({"GITHUB_HEAD_REF": "spec/SPEC-5"}, True),
            ({"CI_MERGE_REQUEST_SOURCE_BRANCH_NAME": "spec/SPEC-5"}, True),
            ({"GITHUB_HEAD_REF": "feat"}, False),
            ({}, False),
        ]
        for env, found in cases:
            with self.subTest(env=env), mock.patch.dict(os.environ):
                for name in ("GITHUB_HEAD_REF", "CI_MERGE_REQUEST_SOURCE_BRANCH_NAME"):
                    os.environ.pop(name, None)
                os.environ.update(env)
                self.assertEqual(testing.change_branch(str(self.root), {**env}), next(iter(env.values()), ""))
                ci, _ = self.run_aidd()
                self.assertEqual(self.ran(ci) == self.ran(local), found, (self.ran(ci), self.ran(local)))
                self.assertEqual(testing.exit_code(ci) == testing.exit_code(local), found)
        self.assertEqual(testing.change_branch(str(self.root), {"GITHUB_HEAD_REF": "x"}), "x")
        git(self.root, "checkout", "-q", "spec/SPEC-5")
        self.assertEqual(testing.change_branch(str(self.root), {"GITHUB_HEAD_REF": "x"}), "spec/SPEC-5", "a checked-out branch wins")

    def test_two_specs_with_one_id_stop_the_run_and_say_why(self):
        self.branch()
        for name in ("SPEC-1.md", "SPEC-1-copy.md"):
            self.put(self.root, f"specs/{name}", spec_text("SPEC-1"))
        self.commit(self.root, "two Specs, one id")
        with self.assertRaises(DocumentError) as stop:
            self.run_aidd()
        self.assertIn("two Specs have the id SPEC-1", str(stop.exception))
        self.assertIn("give one of them a new id", str(stop.exception))

    def test_a_spec_branch_with_no_such_spec_stops_and_names_the_branch_and_the_step(self):
        self.branch("spec/SPEC-9")
        self.put(self.root, "docs/guide.md", "guide\n")
        self.commit(self.root, "docs")
        with self.assertRaises(DocumentError) as stop:
            self.run_aidd()
        self.assertIn("SPEC-9", str(stop.exception))
        self.assertIn("commit SPEC-9", str(stop.exception))


if __name__ == "__main__":
    unittest.main()
