"""`aidd revise <ID> "<why>"` (V20 (3)): an approved Spec reopens in one step. It records what was wrong, which voids
the approval, so the frozen files open to their owners again, and the next Spec approval, whose card says why, freezes
them again."""

import json
import os
import shutil
import unittest
from unittest import mock

from helpers import RepoTemplateCase, aidd_subprocess, git, make_repo

from aidd import config, workitems
from aidd.guard import command_check, edit_check
from aidd.kernel import documents
from aidd.kernel import git as gitops
from aidd.workitems import decision_records

SPEC = "specs/SPEC-220.md"
TEST = "tests/checkout/test_rate_limit.py"


@unittest.skipUnless(shutil.which("git"), "git is required")
class ReviseTests(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", spec=f"02-normal-feature:{SPEC}", approvers=[f"email:{git(root, 'config', 'user.email').strip()}"])

    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {k: v for k, v in os.environ.items() if k != "AIDD_SPEC"}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def approve(self) -> str:
        """Commit the Spec and record a listed Approver's local Spec approval of its hash at that commit."""
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "spec: SPEC-220")
        head = git(self.root, "rev-parse", "HEAD").strip()
        h = workitems.spec_hash((self.root / SPEC).read_text(encoding="utf-8"), gitops.ls_tree(head, str(self.root)))
        decision_records.record_local_approval(decision_records.approve_spec_line("SPEC-220", head), str(self.root))
        return h

    def holds(self) -> bool:
        cfg = config.load_file(config.CONFIG_PATH, str(self.root))
        data = documents.split_front_matter((self.root / SPEC).read_text(encoding="utf-8"), SPEC)[0]
        return workitems.approval_holds(workitems.Observer(self.root, cfg), SPEC, data)

    def revise(self, *args):
        run = aidd_subprocess("revise", *args, cwd=self.root)
        return run.returncode, run.stdout + run.stderr

    def test_a_draft_needs_no_revision(self):
        code, out = self.revise("SPEC-220", "the limit is per card")
        self.assertNotEqual(code, 0)
        self.assertIn("no Spec approval that holds", out)
        self.assertNotIn("revisions", (self.root / SPEC).read_text(encoding="utf-8"))

    def test_revise_reopens_the_spec_and_its_frozen_files(self):
        was = self.approve()
        self.assertTrue(self.holds())
        self.assertEqual(edit_check.check_edit(str(self.root), TEST, "verifier")[0], "deny")  # frozen by the approval
        code, out = self.revise("SPEC-220", "the limit is per card,   not per user")
        self.assertEqual(code, 0, out)
        self.assertIn("SPEC-220 is a draft again: the limit is per card, not per user", out)
        data = documents.split_front_matter((self.root / SPEC).read_text(encoding="utf-8"), SPEC)[0]
        self.assertEqual(data["revisions"][-1]["why"], "the limit is per card, not per user")
        self.assertEqual(data["revisions"][-1]["was"], was)
        self.assertEqual(git(self.root, "status", "--porcelain", "--", SPEC), "")  # recorded on its own commit
        self.assertIn("revise SPEC-220", git(self.root, "log", "-1", "--format=%s"))
        self.assertFalse(self.holds())
        self.assertEqual(edit_check.check_edit(str(self.root), TEST, "verifier")[0], "allow")  # its owner changes it again
        self.assertEqual(edit_check.check_edit(str(self.root), TEST, "developer")[0], "deny")  # and only its owner
        self.assertNotEqual(self.revise("SPEC-220", "again")[0], 0)  # one revision reopens it; it is a draft now

    def test_the_approval_card_says_why_it_was_reopened(self):
        self.approve()
        self.assertEqual(self.revise("SPEC-220", "the limit is per card")[0], 0)
        run = aidd_subprocess("approve", "spec", "SPEC-220", "--show", cwd=self.root)
        shown = json.loads(run.stdout)
        self.assertTrue(shown["revised"].startswith("the limit is per card (reopened "), shown)

    def test_uncommitted_edits_to_the_spec_come_first(self):
        self.approve()
        with (self.root / SPEC).open("a", encoding="utf-8") as fh:
            fh.write("\nAn edit in progress.\n")
        code, out = self.revise("SPEC-220", "the limit is per card")
        self.assertNotEqual(code, 0)
        self.assertIn("not committed", out)

    def test_never_on_the_base_branch(self):
        self.approve()
        git(self.root, "checkout", "-q", "-B", "main")
        code, out = self.revise("SPEC-220", "the limit is per card")
        self.assertNotEqual(code, 0)
        self.assertIn("on its own branch", out)

    def test_only_a_role_that_writes_the_spec_may_revise_it(self):
        """`aidd revise` writes the Spec, so the guard judges it as an edit of the Spec: never the developer's."""
        self.approve()

        def run(role: str, command: str):
            event = {"tool_name": "Bash", "agent_type": f"aidd-team:{role}", "cwd": str(self.root)}
            return command_check.check_command(str(self.root), str(self.root), command, event)

        for command in ('aidd revise SPEC-220 "the limit is per card"', 'uvx aidd revise specs/SPEC-220.md "per card"', "python3 -m aidd revise SPEC-220 x"):
            with self.subTest(command=command):
                decision, why = run("developer", command)
                self.assertEqual(decision, "deny", why)
                self.assertIn("SPEC-220.md", why)
                self.assertEqual(run("architect", command)[0], "allow")
        # From a subfolder, a path is read from there, as the CLI reads it: never another file than the one it writes.
        (self.root / "src").mkdir(exist_ok=True)
        event = {"tool_name": "Bash", "agent_type": "aidd-team:developer", "cwd": str(self.root / "src")}
        decision, why = command_check.check_command(str(self.root), str(self.root / "src"), 'aidd revise ../specs/SPEC-220.md "x"', event)
        self.assertEqual(decision, "deny", why)
        self.assertNotEqual(aidd_subprocess("revise", "specs/SPEC-220.md", "x", cwd=self.root / "src").returncode, 0)  # no src/specs/: no other file

    def test_a_why_is_one_short_sentence(self):
        self.approve()
        self.assertNotEqual(self.revise("SPEC-220", "  ")[0], 0)
        self.assertNotEqual(self.revise("SPEC-220", "x" * 301)[0], 0)
        self.assertTrue(self.holds())


if __name__ == "__main__":
    unittest.main()
