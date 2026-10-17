"""A person decides once, directly, and it works: every note says plainly whether aidd recorded the decision, a refusal
names the way that works where the person is, a failing gate never blocks their Merge approval, and "ship it" holds for
the fix the gate or the reviewer asks for."""

from __future__ import annotations

import os
import shutil
import unittest
from pathlib import Path
from unittest import mock

from helpers import RepoTemplateCase, git
from test_flows import _commit, run_cli, shop, spec_and_tests

from aidd.cli.commands import typed_decisions
from aidd.platforms import local_ship
from aidd.workitems import approval_ledger


def implement(root) -> str:
    return _commit(
        root,
        "feat: discount\n\nAssisted-by: claude-code/claude-opus-5-5",
        {"app/discount.py": "def discount(total, pct):\n    return total - total * pct // 100\n"},
    )


@unittest.skipUnless(shutil.which("git"), "git is required")
class TypedDecisionNotesTests(RepoTemplateCase):
    """A solo, local-first shop with SPEC-1 and its failing test on the branch `discount`."""

    @classmethod
    def build_template(cls, root):
        shop(root)
        spec_and_tests(root)

    def test_a_decision_that_cannot_be_recorded_is_never_passed_off_as_one(self):
        git(self.root, "config", "user.email", "me@work.example")  # not the listed Approver
        said = typed_decisions.record("approve SPEC-1", str(self.root)) or ""
        self.assertIn("could not record it", said)
        self.assertNotIn("never ask them again", said)
        self.assertIn("`git config user.email me@example.com`", said)  # the one-line fix first

    def test_a_recorded_decision_says_so_once(self):
        said = typed_decisions.record("approve SPEC-1", str(self.root)) or ""
        self.assertIn("aidd recorded it from their own words: Approved SPEC-1", said)
        self.assertNotIn("..", said)

    def test_a_crash_while_recording_says_so_instead_of_vanishing(self):
        with mock.patch.object(typed_decisions, "_record_typed", side_effect=RuntimeError("boom")):
            said = typed_decisions.record("approve SPEC-1", str(self.root)) or ""
        self.assertIn("could not record it", said)
        self.assertIn("type it once more", said)

    def test_an_unfinished_spec_is_not_ready_rather_than_approved_and_voided_later(self):
        spec = Path(self.root, "specs/SPEC-1.md")
        spec.write_text(spec.read_text(encoding="utf-8").replace("\nroute: normal", "\nroute: major", 1), encoding="utf-8")
        _commit(self.root, "spec: major, with no observe block yet")
        said = typed_decisions.record("approve SPEC-1", str(self.root)) or ""
        self.assertIn("could not record it", said)
        self.assertIn("not ready", said)
        self.assertIn("observe", said)

    def test_a_merge_approval_is_recorded_while_the_gate_fails_elsewhere(self):
        implement(self.root)
        Path(self.root, "README.md").write_text("outside every scope\n", encoding="utf-8")
        _commit(self.root, "chore: scope creep")
        said = typed_decisions.record("approve merge", str(self.root)) or ""
        self.assertIn("aidd recorded it", said)
        self.assertIn("The gate still fails on scope", said)


@unittest.skipUnless(shutil.which("git"), "git is required")
class WhereThePersonIsTests(unittest.TestCase):
    def test_inside_an_agents_shell_the_refusal_names_the_words_to_type(self):
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}):
            for command, typed in (
                ("aidd approve spec specs/SPEC-1.md", "approve SPEC-1"),
                ("aidd approve merge", "approve merge"),
                ("aidd ship --squash", "ship it"),
                ("aidd approve all --but-major", "approve all but major"),
            ):
                with self.subTest(command=command), self.assertRaises(local_ship.NotAPerson) as caught:
                    local_ship.check_terminal("A decision", command)
                self.assertIn(f"Type `{typed}` at your coding agent's prompt", str(caught.exception))
                self.assertIn(command, str(caught.exception))  # and the terminal way, to copy


@unittest.skipUnless(shutil.which("git"), "git is required")
class ShipItOnAPlatformTests(RepoTemplateCase):
    """Where a platform's gate decides, "ship it" is the person's Merge approval there, then auto-merge: no step left."""

    @classmethod
    def build_template(cls, root):
        shop(root)
        spec_and_tests(root)
        implement(root)
        # A platform repository: a remote and the gate's workflow, so the platform's gate decides.
        Path(root, ".github", "workflows").mkdir(parents=True)
        Path(root, ".github", "workflows", "aidd-gate.yml").write_text("name: aidd\n", encoding="utf-8")
        git(root, "remote", "add", "origin", "https://github.com/acme/shop.git")

    def test_ship_it_approves_with_auto_merge_and_never_ships_locally(self):
        with mock.patch.object(typed_decisions, "_cli", return_value=(0, "Approved merging discount. Auto-merge is on.")) as cli:
            said = typed_decisions.record("ship it", str(self.root)) or ""
        argv = cli.call_args[0][0]
        self.assertEqual((argv[:2], argv[-1]), (["approve", "merge"], "--auto-merge"))
        self.assertIn("aidd recorded it", said)
        self.assertIn("Never run `aidd ship` here", said)

    def test_auto_merge_turns_on_after_the_approving_review(self):
        from aidd.cli.commands import decide
        from aidd.platforms import github

        pr = github.PullRequest("acme/shop", 7, "https://github.com/acme/shop/pull/7", "a" * 40, "me")
        for why, said in ((None, "Auto-merge is on"), ("auto-merge is not allowed for this repository", "Auto-merge is not on (auto-merge")):
            with (
                self.subTest(why=why),
                mock.patch.object(decide, "_platform_target", return_value=(pr, None)),
                mock.patch.object(github, "approve_pull_request", return_value=pr.url),
                mock.patch.object(github, "enable_auto_merge", return_value=why),
                mock.patch("sys.stdout", new_callable=__import__("io").StringIO) as out,
            ):
                self.assertEqual(decide._approve_on_platform("discount", "a" * 40, ask=False, auto_merge=True), 0)
            self.assertIn(said, out.getvalue())


class SignedApprovalsTests(unittest.TestCase):
    def test_an_unsigned_machine_hears_it_before_deciding_not_after(self):
        from types import SimpleNamespace

        from aidd.cli.commands import confirmations
        from aidd.workitems import approval_ledger

        cfg = SimpleNamespace(gates={"local_approvals": "signed"})
        with mock.patch.object(approval_ledger, "is_signing_configured", return_value=False):
            problem = confirmations._signing_problem(cfg) or ""
        self.assertIn("would never count", problem)
        self.assertIn("`git config user.signingkey", problem)
        with mock.patch.object(approval_ledger, "is_signing_configured", return_value=True):
            self.assertIsNone(confirmations._signing_problem(cfg))
        self.assertIsNone(confirmations._signing_problem(SimpleNamespace(gates={})))


@unittest.skipUnless(shutil.which("git"), "git is required")
class ShipItHoldsTests(RepoTemplateCase):
    """ "ship it" said on a head the gate still waits on: the fix that follows ships too, while the Spec stays as approved."""

    @classmethod
    def build_template(cls, root):
        shop(root)
        spec_and_tests(root)
        implement(root)

    def said(self) -> str:
        head = git(self.root, "rev-parse", "HEAD")
        approval_ledger.record_local_approval(approval_ledger.ship_said_line(head, git(self.root, "branch", "--show-current")), str(self.root))
        return head

    def holds(self) -> bool:
        from aidd import config

        cfg = config.load_file(config.CONFIG_PATH, str(self.root))
        return approval_ledger.ship_said_for(cfg, str(self.root), git(self.root, "rev-parse", "HEAD"))

    def test_a_fix_inside_the_work_ships_with_nobody_asked_again(self):
        self.said()
        _commit(
            self.root,
            "fix: round down\n\nAssisted-by: claude-code/claude-opus-5-5",
            {"app/discount.py": "def discount(total, pct):\n    return total - (total * pct) // 100\n"},
        )
        self.assertTrue(self.holds())
        code, out = run_cli(self.root, "ship")
        self.assertEqual(code, 0, out)
        self.assertIn("so nobody is asked again", out)
        self.assertIn("adds 1 commit(s) inside the same work", out)  # what the person has not seen, named
        self.assertIn("fix: round down", out)
        self.assertNotIn("a person runs", out)  # no step printed for anyone: shipping records the approval
        # The record names the decision it rests on, never claiming the person confirmed this head at the prompt.
        record = git(self.root, "log", "-1", "--format=%B", approval_ledger.APPROVALS_REF)
        self.assertRegex(record, r"Aidd-Confirmed-In: ship-it:[0-9a-f]{12}")
        # One "ship it" ships one change: once its work has landed, the next commit on the branch asks again.
        _commit(self.root, "feat: more", {"app/discount.py": "def discount(total, pct):\n    return total\n"})
        self.assertFalse(self.holds())

    def test_the_merge_approval_of_a_fix_is_recorded_under_it(self):
        """On a platform nothing runs `aidd ship`: the agent's `aidd approve merge` records the fixed head under it."""
        self.said()
        _commit(self.root, "fix: round down", {"app/discount.py": "def discount(total, pct):\n    return total - (total * pct) // 100\n"})
        code, out = run_cli(self.root, "test")
        self.assertEqual(code, 0, out)
        code, out = run_cli(self.root, "approve", "merge")
        self.assertEqual(code, 0, out)
        self.assertIn("inside the same work", out)
        record = git(self.root, "log", "-1", "--format=%B", approval_ledger.APPROVALS_REF)
        self.assertIn(f"{approval_ledger.MERGE_TRAILER}: {git(self.root, 'rev-parse', 'HEAD')}", record)
        self.assertRegex(record, r"Aidd-Confirmed-In: ship-it:[0-9a-f]{12}")

    def test_another_branch_carries_nothing_over(self):
        self.said()
        git(self.root, "switch", "-qc", "other")
        _commit(self.root, "fix elsewhere", {"app/discount.py": "def discount(total, pct):\n    return total\n"})
        self.assertFalse(self.holds())

    def test_a_change_to_the_spec_or_its_tests_asks_again(self):
        # A new file in the Specs folder too: a second Spec, or one an agent adds, deletes, or edits.
        for rel in ("specs/SPEC-1.md", "tests/test_discount.py", "specs/SPEC-2.md"):
            with self.subTest(rel=rel):
                git(self.root, "reset", "-q", "--hard", git(self.root, "rev-parse", "HEAD"))
                self.said()
                with open(Path(self.root, rel), "a", encoding="utf-8") as fh:
                    fh.write("\n# changed\n")
                _commit(self.root, f"change {rel}")
                self.assertFalse(self.holds(), rel)


if __name__ == "__main__":
    unittest.main()
