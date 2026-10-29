"""`aidd revise <ID> "<why>"` (V20 (3)): an approved Spec reopens in one step. It records what was wrong, which voids
the approval, so the frozen files open to their owners again, and the next Spec approval, whose card says why, freezes
them again."""

import json
import os
import shutil
import unittest
from unittest import mock

from helpers import RepoTemplateCase, aidd_subprocess, git, make_repo

from aidd import tracking
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
        git(self.root, "commit", "-qm", "spec: SPEC-220", "--allow-empty")
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

    def test_a_stale_approval_keeps_the_tests_frozen_until_the_spec_is_revised(self):
        """An edit that voids the approval never opens the tests: they stay frozen until `aidd revise` records why, so
        no test is weakened before the person approves again. The revision names the hash that was approved."""
        was = self.approve()
        with (self.root / SPEC).open("a", encoding="utf-8") as fh:
            fh.write("\nA later note.\n")
        git(self.root, "commit", "-qam", "docs(spec): a note")
        self.assertFalse(self.holds())  # the approval is stale: it named the Spec as it read before
        decision, why = edit_check.check_edit(str(self.root), TEST, "verifier")
        self.assertEqual(decision, "deny", why)
        self.assertIn("aidd revise SPEC-220", why)
        code, out = self.revise("SPEC-220", "the limit is per card")
        self.assertEqual(code, 0, out)
        data = documents.split_front_matter((self.root / SPEC).read_text(encoding="utf-8"), SPEC)[0]
        self.assertEqual(data["revisions"][-1]["was"], was)  # the approved hash, never the stale one
        self.assertEqual(edit_check.check_edit(str(self.root), TEST, "verifier")[0], "allow")
        self.assertNotEqual(self.revise("SPEC-220", "again")[0], 0)  # reopened once, it is a draft

    def test_an_edit_of_a_frozen_test_section_is_denied_and_a_dependency_bump_passes(self):
        """The guard reads a manifest edit as the Spec hash reads it: a change to the section the Spec freezes is denied
        before it voids the approval, while the rest of the file stays free. Unknown new text (a shell write) is left to
        the gate and the stale approval."""
        from aidd.guard import frozen_files

        spec = (self.root / SPEC).read_text(encoding="utf-8")
        frozen = 'files: [tests/checkout/test_rate_limit.py, "pyproject.toml#tool.pytest"]'
        (self.root / SPEC).write_text(spec.replace("files: [tests/checkout/test_rate_limit.py]", frozen), encoding="utf-8")
        old = '[project]\nname = "shop"\ndependencies = []\n\n[tool.pytest.ini_options]\naddopts = "-q"\n'
        (self.root / "pyproject.toml").write_text(old, encoding="utf-8")
        self.approve()
        cfg = config.load_file(config.CONFIG_PATH, str(self.root))
        held, view = frozen_files.frozen_view(str(self.root), cfg, workitems.active_specs(str(self.root), cfg))

        def why(new):
            return frozen_files.frozen_section_edit(view, held, "pyproject.toml", (old, new))

        weaker = why(old.replace('"-q"', '"-q -k not_rate_limit"'))
        self.assertIn("pyproject.toml#tool.pytest", weaker or "")
        self.assertIn("aidd revise SPEC-220", weaker or "")
        self.assertIsNone(why(old.replace("dependencies = []", 'dependencies = ["requests"]')))  # a dependency bump
        self.assertIsNotNone(why(old + "[[broken"))  # a manifest that does not parse counts as changed
        self.assertIsNotNone(why(None))  # an edit that gives no new text fails closed
        self.assertIsNone(frozen_files.frozen_section_edit(view, held, "pyproject.toml", (None, None)))  # a shell write: the gate
        decision, reason = edit_check.check_edit(str(self.root), "pyproject.toml", "developer", old, old.replace('"-q"', '"-q -x"'))
        self.assertEqual(decision, "deny", reason)
        self.assertIn("a test setting of SPEC-220 frozen by Spec approval", reason)

    def stale_spec(self) -> str:
        """Approve the Spec, then commit an edit of it: the approval stands, stale. The approved hash."""
        was = self.approve()
        with (self.root / SPEC).open("a", encoding="utf-8") as fh:
            fh.write("\nA later note.\n")
        git(self.root, "commit", "-qam", "docs(spec): a note")
        return was

    def assert_tests_denied(self) -> None:
        """The verifier's edit of the frozen test file is denied."""
        decision, why = edit_check.check_edit(str(self.root), TEST, "verifier")
        self.assertEqual(decision, "deny", why)

    def test_the_newest_approval_counts_after_a_revision_and_a_new_approval(self):
        self.stale_spec()
        self.assertEqual(self.revise("SPEC-220", "the limit is per card")[0], 0)
        again = self.approve()  # approved again, at the new hash
        with (self.root / SPEC).open("a", encoding="utf-8") as fh:
            fh.write("\nAnother note.\n")
        git(self.root, "commit", "-qam", "docs(spec): another note")
        self.assert_tests_denied()  # stale again, by the newest approval
        self.assertEqual(self.revise("SPEC-220", "per card again")[0], 0)
        data = documents.split_front_matter((self.root / SPEC).read_text(encoding="utf-8"), SPEC)[0]
        self.assertEqual(data["revisions"][-1]["was"], again)

    def test_an_edit_of_the_working_tree_spec_never_unfreezes_what_was_approved(self):
        self.stale_spec()
        text = (self.root / SPEC).read_text(encoding="utf-8")
        for change in (
            ("route: normal", "route: emergency"),
            ("tests:\n", "tests:\n  mode: with_code\n"),
            ("id: SPEC-220", "id: SPEC-999"),
            ("files: [tests/checkout/test_rate_limit.py]", "files: []"),
        ):
            with self.subTest(change=change[1]):
                (self.root / SPEC).write_text(text.replace(*change, 1), encoding="utf-8")
                self.assert_tests_denied()
        (self.root / SPEC).write_text(text, encoding="utf-8")

    def test_a_committed_id_change_keeps_the_stale_approval(self):
        """An approval follows the file, not only the id it now claims: committing a new id, or a new id and a new path,
        never sheds it."""
        self.stale_spec()
        text = (self.root / SPEC).read_text(encoding="utf-8")
        (self.root / SPEC).write_text(text.replace("id: SPEC-220", "id: SPEC-999", 1), encoding="utf-8")
        git(self.root, "commit", "-qam", "spec: a new id")
        self.assert_tests_denied()
        git(self.root, "mv", SPEC, "specs/SPEC-999.md")
        git(self.root, "commit", "-qm", "spec: and a new path")
        self.assert_tests_denied()

    def test_an_uncommitted_move_with_a_new_id_keeps_the_stale_approval(self):
        """Failing closed: an approval on this branch of an id no active Spec claims now freezes the Spec no approval of
        its own covers, so no uncommitted move or id change sheds it."""
        self.stale_spec()
        text = (self.root / SPEC).read_text(encoding="utf-8")
        (self.root / SPEC).unlink()
        (self.root / "specs/SPEC-777.md").write_text(text.replace("id: SPEC-220", "id: SPEC-777", 1), encoding="utf-8")
        self.assert_tests_denied()
        why = edit_check.check_edit(str(self.root), TEST, "verifier")[1]
        self.assertIn("commit a moved Spec first", why)  # uncommitted, the move is no rename git can pair yet
        self.assertIn("SPEC-220", why)

    def other_spec(self, sid: str, test: str) -> None:
        """Write another Spec beside SPEC-220, with its own id and its own test file."""
        text = (self.root / SPEC).read_text(encoding="utf-8")
        other = text.replace("id: SPEC-220", f"id: {sid}", 1).replace("files: [tests/checkout/test_rate_limit.py]", f"files: [{test}]")
        (self.root / f"specs/{sid}.md").write_text(other, encoding="utf-8")

    def test_a_decoy_that_claims_the_approved_id_sheds_nothing(self):
        self.stale_spec()
        text = (self.root / SPEC).read_text(encoding="utf-8")
        git(self.root, "mv", SPEC, "specs/SPEC-777.md")
        (self.root / "specs/SPEC-777.md").write_text(text.replace("id: SPEC-220", "id: SPEC-777", 1), encoding="utf-8")
        decoy = text.replace("files: [tests/checkout/test_rate_limit.py]", "files: []")
        (self.root / "specs/decoy.md").write_text(decoy, encoding="utf-8")  # claims SPEC-220, freezes nothing
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "spec: a new id, and a decoy")
        self.assert_tests_denied()

    def test_revise_reopens_a_renamed_spec_through_the_branchs_approval(self):
        self.stale_spec()
        text = (self.root / SPEC).read_text(encoding="utf-8")
        git(self.root, "mv", SPEC, "specs/SPEC-777.md")
        (self.root / "specs/SPEC-777.md").write_text(text.replace("id: SPEC-220", "id: SPEC-777", 1), encoding="utf-8")
        git(self.root, "commit", "-qam", "spec: a new id")
        self.assert_tests_denied()
        code, out = self.revise("SPEC-777", "the limit is per card")
        self.assertEqual(code, 0, out)
        self.assertEqual(edit_check.check_edit(str(self.root), TEST, "verifier")[0], "allow")

    def test_a_rebase_then_a_move_with_a_new_id_keeps_the_stale_approval(self):
        self.stale_spec()
        here = git(self.root, "rev-parse", "--abbrev-ref", "HEAD").strip()
        git(self.root, "checkout", "-q", "main")
        (self.root / "NOTES.md").write_text("on main\n", encoding="utf-8")
        git(self.root, "add", "NOTES.md")
        git(self.root, "commit", "-qm", "main moves on")
        git(self.root, "checkout", "-q", here)
        git(self.root, "rebase", "-q", "main")
        text = (self.root / SPEC).read_text(encoding="utf-8")
        git(self.root, "mv", SPEC, "specs/SPEC-777.md")
        (self.root / "specs/SPEC-777.md").write_text(text.replace("id: SPEC-220", "id: SPEC-777", 1), encoding="utf-8")
        git(self.root, "commit", "-qam", "spec: a new id")
        self.assert_tests_denied()

    def test_a_rebase_then_a_move_survives_many_approvals_elsewhere(self):
        """A rebased approval is matched by its change (patch-id), however many newer approvals sit on other branches."""
        self.stale_spec()
        here = git(self.root, "rev-parse", "--abbrev-ref", "HEAD").strip()
        for i in range(12):  # approvals made on other branches, newer than this one's
            git(self.root, "checkout", "-q", "-b", f"other-{i}", "main")
            (self.root / f"note-{i}.md").write_text(f"{i}\n", encoding="utf-8")
            git(self.root, "add", f"note-{i}.md")
            git(self.root, "commit", "-qm", f"other {i}")
            sha = git(self.root, "rev-parse", "HEAD").strip()
            decision_records.record_local_approval(decision_records.approve_spec_line(f"SPEC-5{i:02d}", sha), str(self.root))
        git(self.root, "checkout", "-q", "main")
        (self.root / "NOTES.md").write_text("on main\n", encoding="utf-8")
        git(self.root, "add", "NOTES.md")
        git(self.root, "commit", "-qm", "main moves on")
        git(self.root, "checkout", "-q", here)
        git(self.root, "rebase", "-q", "main")
        text = (self.root / SPEC).read_text(encoding="utf-8")
        git(self.root, "mv", SPEC, "specs/SPEC-777.md")
        (self.root / "specs/SPEC-777.md").write_text(text.replace("id: SPEC-220", "id: SPEC-777", 1), encoding="utf-8")
        git(self.root, "commit", "-qam", "spec: a new id")
        self.assert_tests_denied()

    def test_an_approval_at_an_empty_commit_survives_a_rebase_and_a_move(self):
        """An approval recorded at an empty commit has no patch to match: the branch's own diff naming its id finds it."""
        self.approve()
        self.approve()  # again, at an empty commit on top
        with (self.root / SPEC).open("a", encoding="utf-8") as fh:
            fh.write("\nA later note.\n")
        git(self.root, "commit", "-qam", "docs(spec): a note")
        here = git(self.root, "rev-parse", "--abbrev-ref", "HEAD").strip()
        git(self.root, "checkout", "-q", "main")
        (self.root / "NOTES.md").write_text("on main\n", encoding="utf-8")
        git(self.root, "add", "NOTES.md")
        git(self.root, "commit", "-qm", "main moves on")
        git(self.root, "checkout", "-q", here)
        git(self.root, "rebase", "-q", "--keep-empty", "main")
        text = (self.root / SPEC).read_text(encoding="utf-8")
        git(self.root, "mv", SPEC, "specs/SPEC-777.md")
        (self.root / "specs/SPEC-777.md").write_text(text.replace("id: SPEC-220", "id: SPEC-777", 1), encoding="utf-8")
        git(self.root, "commit", "-qam", "spec: a new id")
        self.assert_tests_denied()

    def test_a_rewritten_move_is_restored_not_revised_in_a_loop(self):
        """A Spec moved and rewritten past what git pairs as a rename is not the approved Spec: revise refuses it, so it
        never records a revision that reopens nothing, again and again."""
        self.stale_spec()
        git(self.root, "rm", "-q", SPEC)
        (self.root / "specs/SPEC-777.md").write_text("---\nid: SPEC-777\ntitle: Something else\n---\n\nAll new words.\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "spec: rewritten as SPEC-777")
        self.assert_tests_denied()
        self.assertNotEqual(self.revise("SPEC-777", "the limit is per card")[0], 0)
        self.assert_tests_denied()

    def test_a_revision_in_an_unrelated_spec_reopens_nothing(self):
        was = self.stale_spec()
        text = (self.root / SPEC).read_text(encoding="utf-8")
        git(self.root, "mv", SPEC, "specs/SPEC-777.md")
        (self.root / "specs/SPEC-777.md").write_text(text.replace("id: SPEC-220", "id: SPEC-777", 1), encoding="utf-8")
        unrelated = text.replace("id: SPEC-220", "id: SPEC-901", 1).replace("files: [tests/checkout/test_rate_limit.py]", "files: []")
        (self.root / "specs/SPEC-901.md").write_text(workitems.add_revision(unrelated, why="unrelated", on="2026-10-28", was=was), encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "spec: a new id, and an unrelated Spec")
        self.assert_tests_denied()

    def test_a_denial_never_sends_the_agent_to_revise_a_spec_whose_approval_holds(self):
        """SPEC-221 approved, then removed, beside SPEC-220 whose approval holds: revising SPEC-220 would throw a good
        approval away and reopen nothing, so the denial says to restore SPEC-221 instead."""
        self.other_spec("SPEC-221", "tests/other/test_221.py")
        (self.root / "tests/other").mkdir(parents=True, exist_ok=True)
        (self.root / "tests/other/test_221.py").write_text("x = 1\n", encoding="utf-8")
        self.approve()  # both Specs at this commit
        head = git(self.root, "rev-parse", "HEAD").strip()
        decision_records.record_local_approval(decision_records.approve_spec_line("SPEC-221", head), str(self.root))
        git(self.root, "rm", "-q", "specs/SPEC-221.md")
        git(self.root, "commit", "-qm", "SPEC-221 moves to its own branch")
        self.approve()  # SPEC-220 approved again at the new head, so its approval holds
        decision, why = edit_check.check_edit(str(self.root), "tests/other/test_221.py", "verifier")
        self.assertEqual(decision, "deny", why)
        self.assertNotIn("aidd revise SPEC-220", why)
        self.assertIn("SPEC-221", why)

    def test_a_removed_spec_restored_revised_and_removed_again_stays_open(self):
        """The denial's own way out: restore the Spec, revise it, and remove it again. The revision on the branch keeps
        it reopened, so a branch that drops a Spec is never frozen for good."""
        self.stale_spec()
        approved = git(self.root, "rev-parse", "HEAD~1").strip()  # the approval's commit, before the note
        git(self.root, "rm", "-q", SPEC)
        git(self.root, "commit", "-qm", "the Spec moves to its own branch")
        self.assert_tests_denied()
        git(self.root, "checkout", approved, "--", SPEC)
        git(self.root, "commit", "-qm", "restore the Spec")
        self.assertEqual(self.revise("SPEC-220", "it moves to its own branch")[0], 0)
        git(self.root, "rm", "-q", SPEC)
        git(self.root, "commit", "-qm", "remove it again")
        decision, why = edit_check.check_edit(str(self.root), TEST)  # with no active Spec, a role writes nothing anyway
        self.assertEqual(decision, "allow", why)
        self.assertNotIn("frozen by Spec approval", edit_check.check_edit(str(self.root), TEST, "verifier")[1])

    def test_revise_reopens_a_spec_that_left_the_branch_in_one_command(self):
        """The denial names `aidd revise <ID>`, and with the Spec gone it restores the approved text to record why,
        then removes it again: no restore by hand, and the branch is never frozen for good."""
        self.stale_spec()
        git(self.root, "rm", "-q", SPEC)
        git(self.root, "commit", "-qm", "the Spec moves to its own branch")
        decision, why = edit_check.check_edit(str(self.root), TEST, "verifier")
        self.assertEqual(decision, "deny", why)
        self.assertIn('`aidd revise SPEC-220 "<what was wrong>"`', why)
        code, out = self.revise("SPEC-220", "it moves to its own branch")
        self.assertEqual(code, 0, out)
        self.assertIn("restored to record the revision", out)
        self.assertFalse((self.root / SPEC).exists())  # removed again
        self.assertEqual(git(self.root, "log", "-2", "--format=%s").splitlines(), ["docs(spec): remove SPEC-220 again", "docs(spec): revise SPEC-220"])
        self.assertEqual(git(self.root, "status", "--porcelain"), "")
        self.assertNotIn("frozen by Spec approval", edit_check.check_edit(str(self.root), TEST, "verifier")[1])
        self.assertNotEqual(self.revise("SPEC-220", "again")[0], 0)  # nothing freezes it now

    def removed(self) -> None:
        """Approve the Spec, edit it, then remove it in a commit: its approval still freezes the tests."""
        self.stale_spec()
        git(self.root, "rm", "-q", SPEC)
        git(self.root, "commit", "-qm", "the Spec leaves the branch")

    def test_a_spec_that_left_is_revised_only_by_its_bare_id(self):
        """A path names the file the guard judges; with the Spec gone, no decoy path reopens it."""
        self.removed()
        for decoy in ("../SPEC-220.md", "docs/SPEC-220.md", "/tmp/nowhere/SPEC-220.md", "specs/SPEC-220.md"):
            with self.subTest(decoy=decoy):
                self.assertNotEqual(self.revise(decoy, "x")[0], 0)
                self.assert_tests_denied()

    def test_a_link_at_the_restore_path_is_never_written_through(self):
        self.removed()
        (self.root / "CLAUDE.md").write_text("the agent's instructions\n", encoding="utf-8")
        (self.root / SPEC).symlink_to("../CLAUDE.md")
        code, out = self.revise("SPEC-220", "x")
        self.assertNotEqual(code, 0, out)  # refused, whichever check names it
        self.assertEqual((self.root / "CLAUDE.md").read_text(encoding="utf-8"), "the agent's instructions\n")
        self.assert_tests_denied()

    def test_a_failed_removal_says_the_revision_is_recorded_and_how_to_finish(self):
        self.removed()
        hook = self.root / ".git" / "hooks" / "pre-commit"
        hook.write_text('#!/bin/sh\ntest -z "$(git diff --cached --diff-filter=D --name-only)"\n', encoding="utf-8")
        hook.chmod(0o755)
        code, out = self.revise("SPEC-220", "x")
        self.assertNotEqual(code, 0)
        self.assertIn("the revision of SPEC-220 is recorded", out)
        self.assertIn("git commit -m", out)

    def test_a_roles_denial_hands_the_revision_to_the_main_session(self):
        self.removed()
        decision, why = edit_check.check_edit(str(self.root), TEST, "verifier")
        self.assertEqual(decision, "deny", why)
        self.assertIn("from the main session", why)

    def test_merge_approval_names_tests_changed_after_a_spec_left_the_branch(self):
        """With no Spec left, no Spec approval shows the reopened tests again, so the Merge approval leads with them."""
        self.removed()
        self.assertEqual(self.revise("SPEC-220", "it moves to its own branch")[0], 0)
        cfg = config.load_file(config.CONFIG_PATH, str(self.root))
        here = os.getcwd()
        os.chdir(self.root)
        try:
            self.assertEqual(tracking.left_branch_changes("HEAD", cfg), [])  # nothing it froze changed yet
            (self.root / TEST).parent.mkdir(parents=True, exist_ok=True)
            (self.root / TEST).write_text("def test_weaker():\n    assert True\n", encoding="utf-8")
            git(self.root, "add", TEST)
            git(self.root, "commit", "-qm", "a weaker test")
            lines = tracking.left_branch_changes("HEAD", cfg)
        finally:
            os.chdir(here)
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("SPEC-220 was approved on this branch at", lines[0])
        self.assertIn(f"{TEST} (+2 -0)", lines[0])
        shown = json.loads(aidd_subprocess("approve", "merge", "--show", cwd=self.root).stdout)
        self.assertTrue(any("then left it" in w for w in shown["warnings"]), shown["warnings"])

    def test_merge_approval_says_nothing_of_a_spec_still_on_the_branch(self):
        self.stale_spec()
        cfg = config.load_file(config.CONFIG_PATH, str(self.root))
        here = os.getcwd()
        os.chdir(self.root)
        try:
            self.assertEqual(tracking.left_branch_changes("HEAD", cfg), [])
        finally:
            os.chdir(here)

    def test_revise_reopens_work_started_over_on_the_same_branch(self):
        self.approve()
        git(self.root, "reset", "-q", "--hard", "main")
        (self.root / "NEW.md").write_text("new work\n", encoding="utf-8")
        git(self.root, "add", "NEW.md")
        git(self.root, "commit", "-qm", "unrelated new work")
        self.assertIn("frozen by Spec approval", edit_check.check_edit(str(self.root), TEST)[1])
        code, out = self.revise("SPEC-220", "started over")
        self.assertEqual(code, 0, out)
        decision, why = edit_check.check_edit(str(self.root), TEST)
        self.assertEqual(decision, "allow", why)

    def test_a_revision_taken_back_out_of_a_spec_no_longer_counts(self):
        """While the Spec is there, its file at HEAD decides: a revision removed from it stops reopening the approval."""
        was = self.stale_spec()
        text = (self.root / SPEC).read_text(encoding="utf-8")
        text = text.replace("id: SPEC-220", "id: SPEC-777", 1)  # a new id, so the branch's approval of SPEC-220 is what freezes it
        git(self.root, "mv", SPEC, "specs/SPEC-777.md")
        (self.root / "specs/SPEC-777.md").write_text(workitems.add_revision(text, why="per card", on="2026-10-28", was=was), encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "spec: a new id, revised")
        self.assertNotIn("frozen by Spec approval", edit_check.check_edit(str(self.root), TEST, "verifier")[1])
        (self.root / "specs/SPEC-777.md").write_text(text, encoding="utf-8")  # the revision taken back out
        git(self.root, "commit", "-qam", "spec: no revision after all")
        self.assert_tests_denied()

    def test_a_removed_spec_freezes_its_files_and_nothing_else(self):
        """With no active Spec left, the approval freezes what it froze, and every other edit is as with no Spec."""
        self.stale_spec()
        git(self.root, "rm", "-q", SPEC)
        git(self.root, "commit", "-qm", "the Spec moves to its own branch")
        self.assert_tests_denied()
        decision, why = edit_check.check_edit(str(self.root), "README.md")
        self.assertEqual(decision, "allow", why)
        self.assertNotIn("SPEC-220", why)

    def test_revise_refuses_a_spec_this_branch_only_carries(self):
        self.approve()
        git(self.root, "checkout", "-qb", "spec/SPEC-300")
        self.other_spec("SPEC-300", "tests/other/test_new.py")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "spec: SPEC-300")
        code, out = self.revise("SPEC-220", "the limit is per card")
        self.assertNotEqual(code, 0)
        self.assertIn("carries from the branch it was built on", out)

    def test_a_stacked_branch_drafts_its_own_spec_freely(self):
        """A branch built on an approved Spec's branch: the parent's approval still holds and freezes its own files, never
        the new Spec's draft tests."""
        self.approve()
        git(self.root, "checkout", "-qb", "spec/SPEC-300")
        self.other_spec("SPEC-300", "tests/other/test_new.py")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "spec: SPEC-300")
        self.assertEqual(edit_check.check_edit(str(self.root), "tests/other/test_new.py", "verifier")[0], "allow")
        self.assert_tests_denied()  # the parent's frozen test stays frozen

    def test_a_spec_whose_file_went_still_freezes_what_was_approved(self):
        self.stale_spec()
        git(self.root, "rm", "-q", SPEC)
        git(self.root, "commit", "-qm", "remove the Spec")
        self.assert_tests_denied()

    def test_several_specs_on_a_branch_keep_the_frozen_tests(self):
        self.approve()
        self.other_spec("SPEC-301", "tests/other/test_more.py")
        decision, why = edit_check.check_edit(str(self.root), TEST)  # the session, with two active Specs
        self.assertEqual(decision, "deny", why)

    def test_a_rename_or_a_rebase_keeps_the_stale_approval(self):
        self.stale_spec()
        git(self.root, "mv", SPEC, "specs/SPEC-220-moved.md")
        git(self.root, "commit", "-qm", "rename the Spec")
        self.assert_tests_denied()
        git(self.root, "mv", "specs/SPEC-220-moved.md", SPEC)
        git(self.root, "commit", "-qm", "rename it back")
        here = git(self.root, "rev-parse", "--abbrev-ref", "HEAD").strip()
        git(self.root, "checkout", "-q", "main")
        (self.root / "NOTES.md").write_text("on main\n", encoding="utf-8")
        git(self.root, "add", "NOTES.md")
        git(self.root, "commit", "-qm", "main moves on")
        git(self.root, "checkout", "-q", here)
        git(self.root, "rebase", "-q", "main")
        self.assert_tests_denied()

    def test_a_squash_an_amend_or_a_rename_keeps_the_stale_approval(self):
        """The approved commit leaves the branch's history, but git's reflog of the branch still holds it."""
        self.stale_spec()
        fork = git(self.root, "merge-base", "HEAD", "main").strip()
        git(self.root, "reset", "-q", "--soft", fork)
        git(self.root, "commit", "-qm", "one commit for the whole change")
        self.assert_tests_denied()
        git(self.root, "commit", "-q", "--amend", "-m", "the same change, reworded")
        self.assert_tests_denied()
        git(self.root, "branch", "-m", "renamed-after-the-squash")
        self.assert_tests_denied()
        self.assertEqual(self.revise("SPEC-220", "the limit is per card")[0], 0)  # revise still reopens it
        self.assertEqual(edit_check.check_edit(str(self.root), TEST, "verifier")[0], "allow")

    def test_a_spec_landed_by_a_squash_freezes_nothing_on_the_branch_that_landed_it(self):
        """The reflog holds both approvals; the newest is the landed text, so neither freezes anything."""
        self.stale_spec()
        self.approve()  # approved again at the edited text, with no revision
        here = git(self.root, "rev-parse", "--abbrev-ref", "HEAD").strip()
        git(self.root, "checkout", "-q", "main")
        git(self.root, "merge", "-q", "--squash", here)
        git(self.root, "commit", "-qm", "land SPEC-220 (squashed)")
        git(self.root, "checkout", "-q", here)
        git(self.root, "reset", "-q", "--hard", "main")
        decision, why = edit_check.check_edit(str(self.root), TEST)
        self.assertEqual(decision, "allow", why)

    def test_a_squash_that_only_takes_the_spec_out_of_the_commit_keeps_the_freeze(self):
        self.stale_spec()
        fork = git(self.root, "merge-base", "HEAD", "main").strip()
        git(self.root, "reset", "-q", "--soft", fork)
        git(self.root, "rm", "-q", "--cached", SPEC)
        git(self.root, "commit", "-q", "--allow-empty", "-m", "the work without its Spec")
        self.assertTrue((self.root / SPEC).exists())
        self.assert_tests_denied()
        (self.root / SPEC).unlink()  # gone from the disk too: removing a Spec never sheds its approval
        self.assert_tests_denied()

    def test_a_reset_that_drops_the_spec_freezes_nothing(self):
        """Work abandoned by `reset --hard` to the fork carries no Spec, so the reflog's approval freezes nothing."""
        self.approve()
        git(self.root, "reset", "-q", "--hard", "main")
        decision, why = edit_check.check_edit(str(self.root), TEST)
        self.assertEqual(decision, "allow", why)

    def test_a_long_run_of_amends_never_pushes_the_approval_out_of_the_reflog(self):
        self.stale_spec()
        fork = git(self.root, "merge-base", "HEAD", "main").strip()
        git(self.root, "reset", "-q", "--soft", fork)
        git(self.root, "commit", "-qm", "squashed")
        for n in range(60):
            git(self.root, "commit", "-q", "--amend", "-m", f"amend {n}")
        self.assert_tests_denied()

    def test_the_list_names_what_changed_since_the_last_approval(self):
        """A Spec that waits for Spec approval again says, in `aidd list`, which files changed since its last approval."""
        self.approve()
        self.assertNotIn("again", aidd_subprocess("list", "--branch", cwd=self.root).stdout)
        self.stale_spec()
        self.assertEqual(self.revise("SPEC-220", "the limit is per card")[0], 0)
        listed = aidd_subprocess("list", "--branch", cwd=self.root).stdout
        self.assertIn("SPEC-220 waits for Spec approval again: 1 file changed since its last approval at", listed)
        self.assertIn("specs/SPEC-220.md (+", listed)

    def test_only_a_committed_revision_of_the_approved_hash_reopens(self):
        self.stale_spec()
        text = (self.root / SPEC).read_text(encoding="utf-8")
        typed = workitems.add_revision(text, why="typed by hand", on="2026-10-28", was="0" * 64)
        (self.root / SPEC).write_text(typed, encoding="utf-8")
        self.assert_tests_denied()  # uncommitted, and of no approved hash
        git(self.root, "commit", "-qam", "docs(spec): a revision of nothing approved")
        self.assert_tests_denied()

    def test_a_revised_spec_stays_open_when_its_id_then_changes(self):
        self.stale_spec()
        self.assertEqual(self.revise("SPEC-220", "the limit is per card")[0], 0)
        text = (self.root / SPEC).read_text(encoding="utf-8")
        (self.root / SPEC).write_text(text.replace("id: SPEC-220", "id: SPEC-221", 1), encoding="utf-8")
        git(self.root, "commit", "-qam", "spec: a new id")
        self.assertEqual(edit_check.check_edit(str(self.root), TEST, "verifier")[0], "allow")

    def test_a_spec_landed_by_a_squash_freezes_nothing_on_a_later_branch(self):
        self.approve()
        here = git(self.root, "rev-parse", "--abbrev-ref", "HEAD").strip()
        git(self.root, "checkout", "-q", "main")
        git(self.root, "merge", "-q", "--squash", here)
        git(self.root, "commit", "-qm", "land SPEC-220 (squashed)")
        git(self.root, "checkout", "-qb", "later")
        with (self.root / SPEC).open("a", encoding="utf-8") as fh:
            fh.write("\nA follow-up.\n")
        git(self.root, "commit", "-qam", "docs(spec): follow-up")
        self.assertEqual(edit_check.check_edit(str(self.root), TEST, "verifier")[0], "allow")

    def test_a_landed_approval_freezes_nothing_on_a_later_branch(self):
        self.approve()
        here = git(self.root, "rev-parse", "--abbrev-ref", "HEAD").strip()
        git(self.root, "checkout", "-q", "main")
        git(self.root, "merge", "-q", "--no-ff", here, "-m", "land SPEC-220")
        git(self.root, "checkout", "-qb", "later")
        with (self.root / SPEC).open("a", encoding="utf-8") as fh:
            fh.write("\nA follow-up.\n")
        git(self.root, "commit", "-qam", "docs(spec): follow-up")
        self.assertEqual(edit_check.check_edit(str(self.root), TEST, "verifier")[0], "allow")

    def test_an_approval_on_another_branch_freezes_nothing_here(self):
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "spec: SPEC-220")
        here = git(self.root, "rev-parse", "--abbrev-ref", "HEAD").strip()
        git(self.root, "checkout", "-qb", "elsewhere")
        with (self.root / SPEC).open("a", encoding="utf-8") as fh:
            fh.write("\nOnly on the other branch.\n")
        git(self.root, "commit", "-qam", "docs(spec): elsewhere")
        decision_records.record_local_approval(decision_records.approve_spec_line("SPEC-220", git(self.root, "rev-parse", "HEAD").strip()), str(self.root))
        git(self.root, "checkout", "-q", here)
        self.assertEqual(edit_check.check_edit(str(self.root), TEST, "verifier")[0], "allow")  # still a draft here
        spec = (self.root / SPEC).read_text(encoding="utf-8")
        (self.root / SPEC).write_text(spec.replace("route: normal", 'route: normal\nstatus: "ready"', 1), encoding="utf-8")
        self.assertEqual(edit_check.check_edit(str(self.root), TEST, "verifier")[0], "allow")  # the records know better

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
