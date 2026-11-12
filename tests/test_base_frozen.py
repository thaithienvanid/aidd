"""A file a Spec froze at the base stays as the base holds it, unless the change revises that Spec.

Invariant: a change that does not revise a Spec cannot rewrite what an approved Spec froze (its test files, its design files, the
script its test command names, and the value of a frozen manifest section) and still pass. Holding the Spec is no revision: a branch
named `spec/<ID>`, `--spec`, or a prose edit of the Spec still stops, and a change that records a revision (a new `revisions` entry)
is said in a note. The delegate's merge check defers it, and `aidd test --require-green`, which a person's branch protection relies
on, stops with the next step. Honest work still passes: other files in the Spec's scope, a new file, a finished Spec's files, a
dependency bump beside a frozen section, a second Spec's new test file, and a revision a person agreed to.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import SAMPLE_SPEC, git
from spec_repo_fixtures import PASS, PY, RepoCase, spec_text
from test_delegation_check import Repo, codes
from test_delegation_spec import SpecCase

from aidd import testing, workitems
from aidd.kernel import git as kernel_git
from aidd.testing import base_frozen

SCRIPT = "import os, sys\nsys.exit(0 if os.path.exists('src/checkout/discount.py') else 1)\n"
FORMATTED = SCRIPT + "\n"
CHEAT = "raise SystemExit(0)\n"
FILES = {
    "tools/verify_discount.py": SCRIPT,
    "tools/helper.py": "VALUE = 1\n",
    "design/discount.md": "# the approved flow\n",
    "tests/test_discount.py": "import unittest\n",
}


def frozen(root: Path, specs_dir: str, base: str, paths: list[str], held: dict | None = None) -> str:
    """The problem `base_frozen_problem` finds in the change from `base` to the checked-out head."""
    return base_frozen.base_frozen_problem(str(root), specs_dir, (base, git(root, "rev-parse", "HEAD")), paths, held or {})[0]


REVISION = 'revisions:\n  - why: "The greeting changes."\n    at: "2026-11-11T09:00:00Z"\n    by: "Maya Lee <maya@example.com>"\n'


def frozen_spec(status: str) -> str:
    """SPEC-220 whose test command runs a script, and whose design file is frozen with it."""
    text = SAMPLE_SPEC.replace("route: normal", f"status: {status}\nroute: normal")
    text = text.replace("[python3, -m, unittest, tests.test_discount]", "[python3, tools/verify_discount.py]")
    text = text.replace('files: ["tests/test_discount.py"]', 'files: ["tests/test_discount.py", "tools/verify_discount.py"]')
    return text.replace("tasks:", "docs:\n  - type: design-files\n    path: design/discount.md\ntasks:", 1)


class DelegateMergeTests(SpecCase):
    def landed(self, status: str = "approved") -> Repo:
        """SPEC-220 approved on `main` (its recorded yes on `ready`), and `feature` starting from `main`."""
        repo = self.repo()
        git(self.root, "checkout", "-q", "main")
        for path, body in FILES.items():
            repo.write(path, body)
        repo.write("specs/SPEC-220.md", frozen_spec("ready"))
        self.delegate_approved(repo.commit("SPEC-220: the Spec and its tests"))
        repo.write("specs/SPEC-220.md", frozen_spec(status))
        repo.commit("Approve SPEC-220")
        git(self.root, "checkout", "-q", "-B", "feature", "main")
        return repo

    def head(self, repo: Repo, files: dict[str, str | None]) -> str:
        from test_delegation_check import note

        for path, body in files.items():
            if body is None:
                (self.root / path).unlink()
            else:
                repo.write(path, body)
        code = repo.commit("Change")
        head = repo.commit("Hand off", "-m", note(code))
        git(self.root, "checkout", "-q", "main")
        return head

    def test_a_change_with_no_spec_defers_for_each_way_of_changing_a_frozen_file(self):
        cases = {
            "the script rewritten to exit 0": {"tools/verify_discount.py": CHEAT},
            "the design file rewritten": {"design/discount.md": "# a new flow\n"},
            "the script renamed": {"tools/verify_discount.py": None, "tools/verify_discount2.py": SCRIPT},
        }
        for name, files in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                self.root = Path(d).resolve()
                repo = self.landed()
                result = repo.check(self.head(repo, files))
                self.assertEqual(codes(result), ["tests_changed"], name)
                self.assertIn("SPEC-220", str(result["reasons"]))
                self.assertIn("spec.revise", str(result["reasons"]), "the message names the next step")

    def test_honest_work_still_passes(self):
        cases = {
            "another file in the Spec's scope": ({"src/checkout/discount.py": "RATE = 0.1\n"}, "approved", []),
            "a finished Spec's script": ({"tools/verify_discount.py": CHEAT}, "done", []),
        }
        for name, (files, status, expected) in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                self.root = Path(d).resolve()
                repo = self.landed(status)
                self.assertEqual(codes(repo.check(self.head(repo, files))), expected, name)


class RunTests(RepoCase):
    """`aidd test --require-green` on the same changes."""

    def landed(self, status: str = "approved") -> None:
        for path, body in FILES.items():
            self.put(self.root, path, body)
        text = spec_text("SPEC-1", status=status, files=("tools/verify_discount.py", "design/discount.md"))
        self.put(self.root, "specs/SPEC-1.md", text.replace(json.dumps([PY, "-c", PASS]), json.dumps([PY, "tools/verify_discount.py"])))
        self.put(self.root, "app/discount.py", "RATE = 0\n")
        self.put(self.root, "src/checkout/discount.py", "RATE = 0\n")
        self.commit(self.root, "SPEC-1 approved")
        self.branch()

    def run_gate(self, files: dict[str, str | None], **kwargs):
        for path, body in files.items():
            if body is None:
                (self.root / path).unlink()
            else:
                self.put(self.root, path, body)
        self.commit(self.root, "Change")
        return self.run_aidd(**kwargs)

    def test_the_gating_run_stops_with_the_next_step_for_a_change_to_a_frozen_file(self):
        cases = {
            "the script rewritten": {"tools/verify_discount.py": CHEAT},
            "the design file rewritten": {"design/discount.md": "# changed\n"},
            "the script renamed": {"tools/verify_discount.py": None, "tools/verify_discount2.py": SCRIPT},
        }
        for name, files in cases.items():
            with self.subTest(name):
                self.fresh()
                self.landed()
                with self.assertRaises(RuntimeError) as stopped:
                    self.run_gate(files, require_green=True, red=False)
                self.assertIn("SPEC-1", str(stopped.exception))
                self.assertIn("spec.revise", str(stopped.exception))

    def test_without_the_gate_it_is_a_note_and_a_quick_check_reads_nothing(self):
        self.landed()
        evidence, notes = self.run_gate({"tools/verify_discount.py": CHEAT}, red=False)
        self.assertTrue(any("SPEC-1" in n and "--require-green" in n for n in notes), notes)
        self.assertEqual(testing.exit_code(evidence, no_red=True), 0, "only the gate fails on it")

    def test_honest_work_passes_the_gate(self):
        cases = {
            "another file in the Spec's scope": ({"app/discount.py": "RATE = 0.1\n"}, "approved"),
            "a finished Spec's script": ({"tools/verify_discount.py": CHEAT}, "done"),
        }
        for name, (files, status) in cases.items():
            with self.subTest(name):
                self.fresh()
                self.landed(status)
                evidence, notes = self.run_gate(files, require_green=True, red=False)
                self.assertFalse([n for n in notes if "froze" in n], notes)
                self.assertEqual(testing.exit_code(evidence, no_red=True), 0, name)

    def test_a_head_that_moves_specs_dir_still_stops_at_the_gate(self):
        self.landed()
        config = (self.root / ".aidd/config.yaml").read_text(encoding="utf-8")
        with self.assertRaises(RuntimeError) as stopped:
            self.run_gate({".aidd/config.yaml": config + "specs_dir: nowhere\n", "tools/verify_discount.py": CHEAT}, require_green=True, red=False)
        self.assertIn("SPEC-1", str(stopped.exception))

    def test_holding_the_spec_is_no_revision_and_a_recorded_revision_is_said(self):
        """A branch named for the Spec, `--spec`, or a prose edit hold it but change nothing its approval froze, so the gate stops as
        for any change; a recorded revision passes the gate with a note that names who approves again (`spec.revise`)."""
        cases = {
            "the branch named for it": ("spec/SPEC-1", lambda text: text, {}, True),
            "--spec names it": ("feat", lambda text: text, {"spec": "specs/SPEC-1.md"}, True),
            "a prose edit of the Spec": ("feat", lambda text: text.replace("Tiny example.", "Tiny example, said another way."), {}, True),
            "a recorded revision": ("feat", lambda text: text.replace("rollback:", REVISION + "rollback:", 1), {}, False),
        }
        for name, (branch, spec, flags, stops) in cases.items():
            with self.subTest(name):
                self.fresh()
                for path, body in FILES.items():
                    self.put(self.root, path, body)
                text = spec_text("SPEC-1", status="approved", files=("tools/verify_discount.py", "design/discount.md"))
                self.put(self.root, "specs/SPEC-1.md", text.replace(json.dumps([PY, "-c", PASS]), json.dumps([PY, "tools/verify_discount.py"])))
                self.commit(self.root, "SPEC-1 approved")
                self.branch(branch)
                files = {"tools/verify_discount.py": CHEAT, "specs/SPEC-1.md": spec((self.root / "specs/SPEC-1.md").read_text(encoding="utf-8"))}
                if stops:
                    with self.assertRaises(RuntimeError) as stopped:
                        self.run_gate(files, require_green=True, red=False, **flags)
                    self.assertIn("revise SPEC-1 in this change", str(stopped.exception))
                else:
                    evidence, notes = self.run_gate(files, require_green=True, red=False, **flags)
                    said = [n for n in notes if "froze" in n]
                    self.assertEqual(len(said), 1, notes)
                    self.assertTrue(said[0].startswith("SPEC-1:") and "approves the Spec again" in said[0], said)
                    self.assertEqual(testing.exit_code(evidence, no_red=True), 0)
                    self.assertEqual(
                        evidence["revised_frozen"],
                        [{"id": "SPEC-1", "files": ["tools/verify_discount.py"]}],
                        "the evidence names the revised Spec and its changed frozen files",
                    )

    def test_the_evidence_names_a_revised_spec_only_when_a_frozen_file_changed_under_a_recorded_revision(self):
        """A revision that changes no frozen file, a change to an unfrozen file, and a run with no revision leave the field out, so a
        person who reads it knows each name in it is a frozen file that changed behind a head-written `revisions` entry."""
        cases = {
            "a revision and a frozen file changed": (
                {"tools/verify_discount.py": CHEAT, "design/discount.md": "# changed\n"},
                True,
                ["design/discount.md", "tools/verify_discount.py"],
            ),
            "a revision and an unfrozen file changed": ({"tools/helper.py": "VALUE = 2\n"}, True, None),
            "no revision and an unfrozen file changed": ({"tools/helper.py": "VALUE = 2\n"}, False, None),
        }
        for name, (files, revise, expected) in cases.items():
            with self.subTest(name):
                self.fresh()
                self.landed()
                text = (self.root / "specs/SPEC-1.md").read_text(encoding="utf-8")
                evidence, _ = self.run_gate(
                    {**files, **({"specs/SPEC-1.md": text.replace("rollback:", REVISION + "rollback:", 1)} if revise else {})}, require_green=True, red=False
                )
                self.assertEqual([e["files"] for e in evidence.get("revised_frozen", [])], [expected] if expected else [], name)

    def test_a_second_spec_adds_its_tests_in_a_new_file_and_is_told_so_for_a_shared_one(self):
        """SPEC-1 froze `tests/test_shared.py`. A change for SPEC-2 that adds a test there stops, with the step that works for it (a new
        file, or waiting until SPEC-1 is done, or revising SPEC-1); the same test in a new file passes."""
        for name, (target, stops) in {"the shared file": ("tests/test_shared.py", True), "a new file": ("tests/test_two.py", False)}.items():
            with self.subTest(name):
                self.fresh()
                self.put(self.root, "tests/test_shared.py", "def test_a():\n    assert True\n")
                self.put(self.root, "specs/SPEC-1.md", spec_text("SPEC-1", status="approved", files=("tests/test_shared.py",)))
                self.commit(self.root, "SPEC-1 approved")
                self.branch("spec/SPEC-2")
                before = (self.root / target).read_text(encoding="utf-8") if (self.root / target).exists() else ""
                files = {target: before + "def test_b():\n    assert True\n", "specs/SPEC-2.md": spec_text("SPEC-2", status="draft", files=(target,))}
                if stops:
                    with self.assertRaises(RuntimeError) as stopped:
                        self.run_gate(files, require_green=True, red=False)
                    self.assertIn("SPEC-1", str(stopped.exception))
                    self.assertIn("in a new file", str(stopped.exception), "the step that works for a second Spec")
                else:
                    _, notes = self.run_gate(files, require_green=True, red=False)
                    self.assertFalse([n for n in notes if "froze" in n], notes)


class RuleTable(RepoCase):
    """`base_frozen_problem` over the Spec's status at the base and how the change holds it."""

    def test_only_a_spec_in_flight_at_the_base_that_the_change_does_not_revise_freezes(self):
        helds = {"not held": (False, False), "held": (False, False), "held and revised": (False, True), "held, its revisions as the base's": (True, False)}
        for status in ("draft", "ready", "approved", "in_progress", "in_review", "done", "rolled_back", "cancelled"):
            for base_revised in (False, True):
                git(self.root, "switch", "-qfC", "case", "main")
                for path, body in FILES.items():
                    self.put(self.root, path, body)
                text = spec_text("SPEC-1", status=status, files=("tools/verify_discount.py",))
                text = text.replace("rollback:", REVISION + "rollback:", 1) if base_revised else text
                self.put(self.root, "specs/SPEC-1.md", text)
                self.commit(self.root, "base")
                base = git(self.root, "rev-parse", "HEAD")
                self.put(self.root, "tools/verify_discount.py", CHEAT)
                self.commit(self.root, "rewrite")
                for held, (on_base, revised) in helds.items():
                    if on_base != base_revised:
                        continue
                    with self.subTest(status=status, held=held):
                        head = text.replace("rollback:", REVISION + "rollback:", 1) if revised else text
                        found = {"SPEC-1": workitems.load_object(head, "specs/SPEC-1.md")[0]} if held != "not held" else {}
                        problem = frozen(self.root, "specs", base, ["tools/verify_discount.py"], found)
                        self.assertEqual(bool(problem), status in ("approved", "in_progress", "in_review") and held != "held and revised")

    def test_each_way_of_changing_a_file_over_the_files_a_spec_froze(self):
        """Changed, reformatted, removed, and renamed away count; a new file, an unfrozen helper, and a file no Spec names do not."""
        cases = {
            "rewritten": ({"tools/verify_discount.py": CHEAT}, True),
            "reformatted": ({"tools/verify_discount.py": FORMATTED}, True),
            "removed": ({"tools/verify_discount.py": None}, True),
            "renamed": ({"tools/verify_discount.py": None, "tools/other.py": SCRIPT}, True),
            "the design file rewritten": ({"design/discount.md": "# new\n"}, True),
            "a new file under a frozen folder": ({"design/extra.md": "# more\n"}, False),
            "an unfrozen helper": ({"tools/helper.py": "VALUE = 2\n"}, False),
            "a file no Spec names": ({"app/other.py": "x = 1\n"}, False),
            "nothing": ({}, False),
        }
        for name, (files, expected) in cases.items():
            with self.subTest(name):
                self.fresh()
                for path, body in FILES.items():
                    self.put(self.root, path, body)
                self.put(self.root, "specs/SPEC-1.md", spec_text("SPEC-1", status="approved", files=("tools/verify_discount.py", "design/*.md")))
                self.commit(self.root, "base")
                base = git(self.root, "rev-parse", "HEAD")
                for path, body in files.items():
                    if body is None:
                        (self.root / path).unlink()
                    else:
                        self.put(self.root, path, body)
                self.commit(self.root, "change")
                paths = git(self.root, "diff", "--name-only", "--no-renames", base, "HEAD").split()
                self.assertEqual(bool(frozen(self.root, "specs", base, paths)), expected, name)

    def landed_base(self, config: str | None) -> str:
        """The base: a Spec approved under `specs/`, its script, and `config` as the config (None: the template's)."""
        for path, body in FILES.items():
            self.put(self.root, path, body)
        self.put(self.root, "specs/SPEC-1.md", spec_text("SPEC-1", status="approved", files=("tools/verify_discount.py",)))
        if config == "":
            (self.root / ".aidd/config.yaml").unlink()  # a first adoption
        elif config is not None:
            self.put(self.root, ".aidd/config.yaml", config)
        self.commit(self.root, "base")
        return git(self.root, "rev-parse", "HEAD")

    def test_the_head_cannot_hide_a_base_spec_by_moving_specs_dir_or_breaking_the_base_config(self):
        """Where the base's Specs are read comes from the base (`base_view.spec_dirs`), so the head only adds folders. A base config
        that exists and does not load stops the check with a step; a base with no config (a first adoption) scans the head's folder."""
        cases = {
            "the head names an empty folder": (None, "nowhere", True),
            "the head names the real folder": (None, "specs", True),
            "the base config does not load": ("tests: [unclosed\n", "nowhere", True),
            "a first adoption, the head names the folder": ("", "specs", True),
            "a first adoption, the head names an empty folder": ("", "nowhere", False),
        }
        for name, (base_config, head_dir, expected) in cases.items():
            with self.subTest(name):
                self.fresh()
                base = self.landed_base(base_config)
                self.put(self.root, "tools/verify_discount.py", CHEAT)
                self.commit(self.root, "rewrite")
                problem = frozen(self.root, head_dir, base, ["tools/verify_discount.py"])
                self.assertEqual(bool(problem), expected, (name, problem))
                if base_config and "load" in name:
                    self.assertIn("does not load", problem)
                    self.assertIn("then run `aidd test` again", problem, "the next step")

    def test_a_repository_of_many_approved_specs_costs_the_same_git_reads(self):
        """The Specs at the base are read in one pass, so the git reads of a check are the same for 50 approved Specs and for 200."""
        reads = []
        made = 0
        for total in (50, 200):
            for n in range(made, total):
                self.put(self.root, f"specs/SPEC-{n + 1}.md", spec_text(f"SPEC-{n + 1}", status="approved", files=(f"checks/c{n}.py", f"checks/d{n}/**")))
            made = total
            self.put(self.root, "app/discount.py", f"RATE = {total}\n")
            self.commit(self.root, "base")
            base = git(self.root, "rev-parse", "HEAD")
            self.put(self.root, "app/discount.py", f"RATE = {total + 1}\n")
            self.commit(self.root, "change")
            with mock.patch.object(kernel_git, "_git", wraps=kernel_git._git) as calls:
                self.assertEqual(frozen(self.root, "specs", base, ["app/discount.py"]), "")
            reads.append(calls.call_count)
        self.assertGreater(reads[0], 0, "the check read nothing from git, so this counts nothing")
        self.assertEqual(reads[0], reads[1], "the git reads of a check grew with the number of Specs")


if __name__ == "__main__":
    unittest.main()
