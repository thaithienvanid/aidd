"""A property-based sweep of the guard against real git: the generator in `guard_shell_forms` dresses a core of
ref-moving git commands in every shell form, and the oracle's own harness judges each one. The guard reads the line,
then bash and git run it in a throwaway copy, and a line the guard allowed that git moved is a bypass.

It reuses `tests/test_guard_ref_oracle.py`'s harness (its template repository and its `judge`), so the two never
drift. A small fixed-seed sample runs here in the normal suite; a larger sample, seeded by the ISO week, runs weekly in
CI (the `guard-sweep` job of `.github/workflows/ci.yml`) with `AIDD_GUARD_SWEEP_PER_CATEGORY` and `AIDD_GUARD_SWEEP_SEED=week`, and its
failure prints each allowed line that moved, ready to paste back here as a case.
"""

from __future__ import annotations

import datetime as dt
import os
import shutil
import unittest

import guard_shell_forms
import test_guard_ref_oracle as oracle

# A fixed seed for the suite, so the sample is the same on every machine and in every run here.
FIXED_SEED = 2026
PER_CATEGORY = int(os.environ.get("AIDD_GUARD_SWEEP_PER_CATEGORY", "20"))


def _seed() -> int:
    """The suite's fixed seed, or the ISO week when CI asks for a rotating sample (`AIDD_GUARD_SWEEP_SEED=week`)."""
    asked = os.environ.get("AIDD_GUARD_SWEEP_SEED")
    if not asked:
        return FIXED_SEED
    if asked == "week":
        year, week, _ = dt.date.today().isocalendar()
        return year * 100 + week
    return int(asked)


@unittest.skipUnless(oracle.BASH and shutil.which("git"), "the sweep needs bash and git to judge what moves")
class GuardShellSweepTests(unittest.TestCase):
    # Borrow the oracle's harness rather than build a second one: the shared template repository, the copy per case,
    # the guard verdict, the real-git run, and the side-by-side `judge`. `setUpClass` builds the template onto this
    # class, exactly as the oracle builds it onto its own.
    fresh = oracle.RefOracleTests.fresh
    denied = oracle.RefOracleTests.denied
    run_bash = oracle.RefOracleTests.run_bash
    judge = oracle.RefOracleTests.judge
    on_explore = oracle.RefOracleTests.on_explore
    records_written = oracle.RefOracleTests.records_written
    base_moved = oracle.RefOracleTests.base_moved

    @classmethod
    def setUpClass(cls):
        oracle.RefOracleTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        oracle.RefOracleTests.tearDownClass.__func__(cls)

    def _sweep(self, category: str, moved) -> None:
        lines = guard_shell_forms.generate(category, _seed(), PER_CATEGORY)
        bypasses, moves = self.judge(lines, moved)
        self.assertGreaterEqual(moves, max(3, len(lines) // 5), f"the sweep must see real {category} moves, or it proves nothing")
        self.assertEqual(bypasses, [], f"the guard allowed these, and git moved {category}:\n" + "\n".join(bypasses))

    def test_no_generated_line_moves_the_base_branch_unseen(self):
        self._sweep("base", self.base_moved)

    def test_no_generated_line_lands_on_a_explore_branch_unseen(self):
        self._sweep("explore", self.on_explore)

    def test_no_generated_line_writes_the_decision_records_unseen(self):
        self._sweep("decisions", self.records_written)

    def test_the_sample_is_the_same_for_a_seed_and_omits_the_guards_documented_limits(self):
        for category in ("base", "explore", "decisions"):
            first = guard_shell_forms.generate(category, 7, 30)
            self.assertEqual(first, guard_shell_forms.generate(category, 7, 30), "the same seed gives the same sample")
            # The documented limits (SECURITY.md): an alias expanded in the shell, a script a shell runs from a file or
            # a download, and writers outside the documented list. The generator never emits them, so every line it
            # emits is one the guard is meant to read.
            for line in first:
                self.assertNotIn("shopt", line, line)
                self.assertNotIn("curl", line, line)
                self.assertNotIn(".sh", line, line)


@unittest.skipUnless(shutil.which("git"), "the claims need a git repository")
class ConfirmedClaimSweepTests(unittest.TestCase):
    """The security fix: under a standing approval the agent may run `aidd land` itself, but never claim the person
    confirmed elsewhere, with `--confirmed` or any prefix of it, in any shell form."""

    def setUp(self):
        import tempfile
        from pathlib import Path

        from helpers import git

        from aidd import workitems

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        git(self.root, "init", "-q", "-b", "main")
        for k, v in (("user.email", "me@example.com"), ("user.name", "Me"), ("commit.gpgsign", "false")):
            git(self.root, "config", k, v)
        Path(self.root, ".aidd").mkdir()
        cfg = 'aidd_version: "1.0.0"\nprofile: solo\nowners:\n  approvers: ["email:me@example.com"]\n'
        Path(self.root, ".aidd", "config.yaml").write_text(cfg, encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "adopt")
        workitems.record_local_approval(workitems.standing_line("all"), self.root)

    def test_every_claim_is_denied_where_the_plain_command_is_allowed(self):
        self.assertFalse(oracle.RefOracleTests.denied(self, oracle.Path(self.root), "aidd land"), "the standing approval lets it run")
        lines = guard_shell_forms.confirmed_claims(_seed(), PER_CATEGORY * 3)
        self.assertEqual(lines, guard_shell_forms.confirmed_claims(_seed(), PER_CATEGORY * 3), "the same seed gives the same sample")
        allowed = [line for line in lines if not oracle.RefOracleTests.denied(self, oracle.Path(self.root), line)]
        self.assertEqual(allowed, [], "the guard let these claim the person confirmed elsewhere")


@unittest.skipUnless(oracle.BASH and shutil.which("git"), "the sweep needs bash to judge what a new agent receives")
class LaunchPromptSweepTests(unittest.TestCase):
    """The security fix: an agent never starts another agent through Orca with a person's decision as its first prompt,
    in any shell form. The oracle's fake Orca CLI logs the prompt bash hands it, and the prompt hook's parser judges it."""

    received = oracle.LaunchPromptOracleTests.received
    bypasses = oracle.LaunchPromptOracleTests.bypasses

    @classmethod
    def setUpClass(cls):
        oracle.LaunchPromptOracleTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        oracle.LaunchPromptOracleTests.tearDownClass.__func__(cls)

    def test_no_generated_line_starts_an_agent_with_a_decision_unseen(self):
        lines = guard_shell_forms.launch_prompts(_seed(), PER_CATEGORY * 2)
        self.assertEqual(lines, guard_shell_forms.launch_prompts(_seed(), PER_CATEGORY * 2), "the same seed gives the same sample")
        bypasses, decided = self.bypasses(lines)
        self.assertEqual(decided, len(lines), "each line must hand a new agent a decision, or the sweep proves nothing")
        self.assertEqual(bypasses, [], "the guard allowed these, and a new agent got a decision as its prompt:\n" + "\n".join(bypasses))

    def test_no_agent_started_under_arch_with_a_decision_is_allowed(self):
        """macOS `arch` runs the program after its options. The guard alone judges these, so they run on any system."""
        lines = guard_shell_forms.arch_agent_starts(_seed(), PER_CATEGORY * 2)
        self.assertEqual(lines, guard_shell_forms.arch_agent_starts(_seed(), PER_CATEGORY * 2), "the same seed gives the same sample")
        allowed = [line for line in lines if not oracle.RefOracleTests.denied(self, self.root, line)]
        self.assertEqual(allowed, [], "the guard allowed these, and `arch` started an agent with a decision as its prompt")


if __name__ == "__main__":
    unittest.main()
