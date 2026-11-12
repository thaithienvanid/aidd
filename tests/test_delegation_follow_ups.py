"""Two guards on what the delegation's records mean elsewhere. `aidd status` names a delegated commit that no delegate's
accept covers, and `aidd risk --suggest` never counts a delegate's answer as a person's yes to a rule."""

import tempfile
import unittest
from pathlib import Path

from helpers import aidd_subprocess, git, hermetic_environ
from test_delegation_check import NAME, config_text

from aidd import config, records, risk

TRAILER = "Delegation: " + "b" * 40


def accept(root: Path, tree: str, action: str = "git.merge", **covers) -> None:
    data = {
        "action": action,
        "covers": {"tree": tree, **covers},
        "outcome": "accept",
        "reason": "green and in scope",
        "check": "20261108T101500123Z-1a2b3c4d",
        "delegation_commit": "b" * 40,
    }
    with records.written_by_delegation():
        records.add_record("delegate_answer", data, by=config.DECIDED_BY, cwd=str(root))


class StatusFlagsACheckMismatchTests(unittest.TestCase):
    """Invariant: for every commit on the default branch that claims a delegated yes in a `Delegation` trailer, `aidd status`
    names it unless an accept of the delegate's own covers that commit's tree."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        git(self.root, "init", "-q", "-b", "main")
        (self.root / ".aidd").mkdir()
        (self.root / ".aidd/config.yaml").write_text(config_text(), encoding="utf-8")
        (self.root / "app.py").write_text("print('a')\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, *NAME, "commit", "-q", "-m", "setup")

    def status(self) -> str:
        out = aidd_subprocess("status", cwd=self.root, env=hermetic_environ())
        self.assertEqual(out.returncode, 0, out.stderr)
        return out.stdout

    def claim(self, text: str, message: str = "Merge it") -> str:
        """A commit on main that claims a delegated yes; its tree."""
        (self.root / "app.py").write_text(text, encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, *NAME, "commit", "-q", "-m", message, "-m", TRAILER)
        return git(self.root, "rev-parse", "HEAD^{tree}")

    def test_a_claim_with_no_accept_or_with_another_trees_accept_is_named_and_one_that_matches_is_not(self):
        tree = self.claim("print('b')\n")
        self.assertIn("Not on record", self.status(), "no accept at all")
        accept(self.root, "e" * 40)
        self.assertIn("Not on record", self.status(), "an accept of another tree")
        accept(self.root, tree)
        self.assertNotIn("Not on record", self.status(), "an accept of this tree")
        self.assertIn("accept on", self.status())

    def test_an_accept_a_session_wrote_under_its_own_name_covers_nothing(self):
        tree = self.claim("print('c')\n")
        data = {
            "action": "git.merge",
            "covers": {"tree": tree},
            "outcome": "accept",
            "reason": "x",
            "check": "20261108T101500123Z-1a2b3c4d",
            "delegation_commit": "b" * 40,
        }
        with records.written_by_delegation():
            records.add_record("delegate_answer", data, by="agent:claude-code/claude-opus-5-5", cwd=str(self.root))
        self.assertIn("Not on record", self.status())

    def test_a_commit_with_no_claim_is_not_named(self):
        (self.root / "app.py").write_text("print('d')\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, *NAME, "commit", "-q", "-m", "A change by hand")
        self.assertNotIn("Not on record", self.status())


class SuggestSkipsDelegateRecordsTests(unittest.TestCase):
    """Invariant: `aidd risk --suggest` counts a person's `decision` records and nothing else, so a delegate's answers, any
    number of them, never suggest lowering a rule."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "commit", "-q", "--allow-empty", "-m", "init")

    def suggested(self) -> list[str]:
        found = risk.rule_suggestions(risk.rule_set(None), str(self.root))
        return [s["action"] for s in found["suggestions"]]

    def test_a_delegates_accepts_never_suggest_a_rule_and_a_persons_yeses_do(self):
        for _ in range(15):
            accept(self.root, "e" * 40, action="git.push", branch="staging")
        self.assertEqual(self.suggested(), [], "fifteen accepts of the delegate's own")
        decision = {
            "action": "git.push",
            "question": {"type": "yes_no", "text": "Push?"},
            "covers": {"branch": "staging"},
            "answer": {"outcome": "accept", "words": "yes", "by": "Ada"},
        }
        for _ in range(10):
            records.add_record("decision", decision, by="agent:claude-code/claude-opus-5-5", cwd=str(self.root))
        self.assertEqual(self.suggested(), ["git.push"], "ten yeses of a person's")


if __name__ == "__main__":
    unittest.main()
