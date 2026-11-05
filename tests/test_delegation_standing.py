"""A delegation counts only from the default branch's tip. When the checked-out branch's config sets one that the tip
does not hold, `aidd doctor` and `aidd status` say it does not count yet, and what to do."""

import tempfile
import unittest
from pathlib import Path

from helpers import aidd_subprocess, git, hermetic_environ

from aidd import config, delegation
from aidd.setup import delegation_wiring

BASE = 'aidd_version: "1.0.0"\nprofile: solo\n'
BLOCK = 'delegation:\n  set_by: "Maya Lee <maya@users.noreply.github.com>"\n  decides: [spec.approve, git.push, git.merge, pr.merge]\n  reserved: []\n  default_branch: "main"\n  review_due: "2099-01-01"\n'


class StandingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / "repo"
        (self.root / ".aidd").mkdir(parents=True)
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.name", "Maya Lee")
        git(self.root, "config", "user.email", "maya@users.noreply.github.com")
        self.write(BASE)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "start")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, text: str) -> None:
        (self.root / config.CONFIG_PATH).write_text(text, encoding="utf-8")

    def commit(self, message: str) -> None:
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", message)

    def block(self) -> dict:
        return dict(config.load_file(config.CONFIG_PATH, str(self.root)).get("delegation") or {})

    def note(self) -> str:
        return delegation.not_yet_on_default_note(str(self.root), self.block())

    def test_a_delegation_on_a_branch_only_does_not_count_and_the_note_says_the_next_step(self):
        git(self.root, "checkout", "-q", "-b", "spec/SPEC-1")
        self.write(BASE + BLOCK)
        self.commit("delegate")
        note = self.note()
        self.assertIn("spec/SPEC-1", note)
        self.assertIn("does not count until it is on main", note)
        self.assertIn("merge", note, "the next step")
        self.assertLessEqual(max(len(s.split()) for s in note.replace("`", "").split(". ")), 35)

    def test_a_delegation_the_default_branch_holds_says_nothing(self):
        self.write(BASE + BLOCK)
        self.commit("delegate")
        git(self.root, "checkout", "-q", "-b", "spec/SPEC-1")
        self.assertEqual(self.note(), "")

    def test_an_uncommitted_delegation_on_the_default_branch_says_to_commit_it(self):
        self.write(BASE + BLOCK)
        note = self.note()
        self.assertIn("does not count until it is on main", note)
        self.assertIn("commit", note)

    def test_a_default_branch_this_clone_lacks_says_nothing(self):
        self.write(BASE + BLOCK.replace('"main"', '"trunk"'))
        self.assertEqual(self.note(), "")

    def test_no_delegation_says_nothing(self):
        self.assertEqual(delegation.not_yet_on_default_note(str(self.root), {}), "")

    def test_doctor_warns_with_the_note(self):
        git(self.root, "checkout", "-q", "-b", "spec/SPEC-1")
        self.write(BASE + BLOCK)
        self.commit("delegate")
        cfg = config.load_file(config.CONFIG_PATH, str(self.root))
        warned = [m for level, m in delegation_wiring.doctor_lines(self.root, cfg) if level == "warn"]
        self.assertIn(self.note(), warned)

    def test_status_says_it_before_the_digest(self):
        git(self.root, "checkout", "-q", "-b", "spec/SPEC-1")
        self.write(BASE + BLOCK)
        self.commit("delegate")
        out = aidd_subprocess("status", cwd=self.root, env=hermetic_environ())
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn(self.note(), out.stdout)
        git(self.root, "checkout", "-q", "main")
        git(self.root, "merge", "-q", "--ff-only", "spec/SPEC-1")
        again = aidd_subprocess("status", cwd=self.root, env=hermetic_environ())
        self.assertNotIn("does not count", again.stdout)


if __name__ == "__main__":
    unittest.main()
