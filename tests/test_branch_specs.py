"""A branch binds only its own Spec: one built on another Spec's branch (`spec/SPEC-3` on `spec/SPEC-1`) carries
SPEC-1 too, and SPEC-1's scope must not bind SPEC-3's work."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import git, make_repo

from aidd import config, workitems
from aidd.guard import edit_check

SPEC = """---
kind: spec
id: {id}
title: {id}
route: normal
tasks:
  - id: T1
    title: build it
    scope: [{scope}]
tests:
  files: [tests/test_{name}.py]
---
"""


@unittest.skipUnless(shutil.which("git"), "git is required")
class BranchSpecTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_repo(Path(tmp.name) / "r", branch="spec/SPEC-1")
        self.cfg = config.load_file(config.CONFIG_PATH, str(self.root))
        self.write("specs/SPEC-1.md", SPEC.format(id="SPEC-1", scope="app/cart.py", name="cart"))
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "spec: SPEC-1")
        self.env = mock.patch.dict(os.environ, {k: v for k, v in os.environ.items() if k != "AIDD_SPEC"}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def write(self, rel: str, text: str) -> None:
        (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.root / rel).write_text(text, encoding="utf-8")

    def active(self) -> list[str]:
        return [rel for rel, _ in workitems.active_specs(str(self.root), self.cfg)]

    def test_a_stacked_branch_binds_its_own_spec_once_it_exists(self):
        git(self.root, "switch", "-qc", "spec/SPEC-3")
        self.assertEqual(self.active(), ["specs/SPEC-1.md"])  # SPEC-3 is not written yet: what the branch carries binds
        self.write("specs/SPEC-3.md", SPEC.format(id="SPEC-3", scope="app/discount.py", name="discount"))
        self.assertEqual(self.active(), ["specs/SPEC-3.md"])
        self.assertEqual(edit_check.check_edit(str(self.root), "specs/SPEC-3.md", "architect")[0], "allow")
        self.assertEqual(edit_check.check_edit(str(self.root), "tests/test_discount.py", "verifier")[0], "allow")  # SPEC-3's test file
        self.assertEqual(edit_check.check_edit(str(self.root), "tests/test_cart.py", "verifier")[0], "deny", "SPEC-1's files are not SPEC-3's")

    def test_a_branch_named_for_no_spec_keeps_every_spec_it_changes(self):
        git(self.root, "switch", "-qc", "feature/issue-42")
        self.assertEqual(self.active(), ["specs/SPEC-1.md"])
        git(self.root, "switch", "-qc", "spec/spec-1-again")
        self.assertEqual(self.active(), ["specs/SPEC-1.md"])

    def test_a_branch_named_for_a_spec_it_does_not_touch_never_borrows_its_scope(self):
        git(self.root, "switch", "-q", "main")
        git(self.root, "merge", "-q", "--ff-only", "spec/SPEC-1")  # SPEC-1 is on the base now, with its scope
        git(self.root, "switch", "-qc", "work/SPEC-1")  # named for SPEC-1, from the base: the branch changes no Spec
        self.write("specs/SPEC-9.md", SPEC.format(id="SPEC-9", scope="app/other.py", name="other"))
        self.assertEqual(self.active(), ["specs/SPEC-9.md"], "the name picks nothing the branch does not change")

    def test_aidd_spec_still_wins(self):
        git(self.root, "switch", "-qc", "spec/SPEC-3")
        self.write("specs/SPEC-3.md", SPEC.format(id="SPEC-3", scope="app/discount.py", name="discount"))
        with mock.patch.dict(os.environ, {"AIDD_SPEC": "specs/SPEC-1.md"}):
            self.assertEqual(self.active(), ["specs/SPEC-1.md"])


class GateDiscoveryTests(unittest.TestCase):
    """The gate finds the Specs a diff changes: a work item that does not parse is one it fails (`spec.unparsable`),
    never one it reads as no Spec; a plain page and a Spec's own notes are no work item."""

    def test_a_work_item_that_does_not_parse_is_kept_for_the_gate_to_fail(self):
        heads = {
            "specs/SPEC-1.md": "---\nkind: spec\nid: SPEC-1\n---\n",
            "specs/SPEC-2.md": '---\nkind: spec\nstatus: "a"\nstatus: "b"\n---\n',  # two status lines
            "specs/SPEC-3.md": "kind: spec, but its --- lines are gone\n",  # no header: no work item, whatever its name
            "specs/ADR-0001.md": "# Use Postgres\n",  # a plain note named like a work item
            "specs/README.md": "# Specs\n",  # a plain page
            "specs/SPEC-1/notes.md": "Notes.\n",  # a Spec's own document
            "specs/EPIC-1.md": "---\nkind: epic\nid: EPIC-1\n---\n",  # parses, and is no Spec
            "specs/archive/SPEC-4.md": "---\nkind: spec\nid: [SPEC-4\n---\n",  # a subfolder, as discovery reads one
        }
        files = [{"path": p} for p in heads]
        self.assertEqual(workitems.find_specs_in_diff(files, "specs", heads.get), ["specs/SPEC-1.md"])  # real Specs only
        broken = workitems.unparsable_work_items(files, "specs", heads.get)
        self.assertEqual([p for p, _ in broken], ["specs/SPEC-2.md", "specs/archive/SPEC-4.md"])
        self.assertIn("appears twice", broken[0][1])


if __name__ == "__main__":
    unittest.main()
