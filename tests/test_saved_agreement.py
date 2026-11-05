"""A run that cannot record a person's agreement to an Intent (the commit asks in the harness, and a headless run cannot
answer the prompt) saves the edit as `.aidd/returns/<ID>/agree.patch`. `aidd status` then gives the person one command for
their own terminal, which records the agreement as their own act."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import aidd_subprocess, git, hermetic_environ, open_work

from aidd import config
from aidd.workitems import saved_agreement

PERSON = "Maya Lee <maya@users.noreply.github.com>"
INTENT = (
    '---\naidd_version: "1.0.0"\ntype: intent\nid: INTENT-1\ntitle: "Plan"\ngoal: "g by 2027-01-01"\n{agreed}'
    "slices: [{{id: SPEC-1, title: one}}]\n---\n\n## Problem\n"
)
AGREED = f'agreed_by: "{PERSON}"\nagreed_at: "2026-11-10T09:12:00Z"\n'
WAITING = "Show me INTENT-1 to agree to, then wait for my answer"


@unittest.skipUnless(shutil.which("git") and shutil.which("sh"), "git and sh are required")
class SavedAgreementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / "repo"
        (self.root / "specs").mkdir(parents=True)
        (self.root / ".aidd").mkdir()
        (self.root / ".aidd/config.yaml").write_text('aidd_version: "1.0.0"\nprofile: solo\n', encoding="utf-8")
        (self.root / ".gitignore").write_text(config.OUTPUT_IGNORE + "\n", encoding="utf-8")  # as `aidd init` writes it
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.name", "Maya Lee")
        git(self.root, "config", "user.email", "maya@users.noreply.github.com")
        self.file = self.root / "specs" / "INTENT-1.md"
        self.file.write_text(INTENT.format(agreed=""), encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "plan")

    def tearDown(self):
        self.tmp.cleanup()

    def save_patch(self) -> Path:
        """What the stopped run leaves: the agreement as a diff, the working tree back as it was."""
        self.file.write_text(INTENT.format(agreed=AGREED), encoding="utf-8")
        patch = self.root / ".aidd/returns/INTENT-1/agree.patch"
        patch.parent.mkdir(parents=True)
        patch.write_text(git(self.root, "diff", "--", "specs/INTENT-1.md") + "\n", encoding="utf-8")
        git(self.root, "checkout", "--", "specs/INTENT-1.md")
        return patch

    def step(self) -> dict:
        return open_work(self.root)[0]["next"]

    def test_with_no_saved_patch_the_step_is_unchanged(self):
        self.assertEqual((self.step()["code"], self.step()["words"]), ("intent.agree", WAITING))

    def test_a_saved_patch_gives_the_person_one_command_in_the_words_and_the_sentence(self):
        self.save_patch()
        step = self.step()
        self.assertEqual(step["code"], "intent.agree")
        words = step["words"]
        for part in ("git apply --include=specs/INTENT-1.md .aidd/returns/INTENT-1/agree.patch", "git add specs/INTENT-1.md", "Agreed-by:"):
            self.assertIn(part, words)
        self.assertIn(words, step["what"], "the plain-text status shows the sentence, not the words")
        self.assertIn("top folder", step["what"])

    def test_the_command_records_the_persons_agreement_as_their_commit(self):
        self.save_patch()
        done = subprocess.run(self.step()["words"], shell=True, cwd=self.root, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(git(self.root, "log", "-1", "--format=%an <%ae>"), PERSON)
        self.assertIn(f"Agreed-by: {PERSON}", git(self.root, "log", "-1", "--format=%B"))
        self.assertEqual(git(self.root, "status", "--porcelain"), "")
        self.assertNotEqual(open_work(self.root)[0]["next"]["code"], "intent.agree", "a commit with the trailer records the agreement")
        checked = aidd_subprocess("validate", "specs/INTENT-1.md", cwd=self.root, env=hermetic_environ())
        self.assertNotIn("Agreed-by", checked.stdout + checked.stderr)

    def test_the_command_applies_the_intent_alone(self):
        patch = self.save_patch()
        other = self.root / "other.txt"
        other.write_text("a\n", encoding="utf-8")
        git(self.root, "add", "other.txt")
        git(self.root, "commit", "-q", "-m", "other")
        other.write_text("b\n", encoding="utf-8")
        edit = git(self.root, "diff", "--", "other.txt") + "\n"
        git(self.root, "checkout", "--", "other.txt")
        patch.write_text(patch.read_text(encoding="utf-8") + edit, encoding="utf-8")
        subprocess.run(self.step()["words"], shell=True, cwd=self.root, capture_output=True, check=True, stdin=subprocess.DEVNULL)
        self.assertEqual(other.read_text(encoding="utf-8"), "a\n", "a patch edit outside the Intent is not applied")

    def test_the_commit_holds_the_intent_file_alone_when_another_file_is_staged(self):
        self.save_patch()
        (self.root / "staged.txt").write_text("x\n", encoding="utf-8")
        git(self.root, "add", "staged.txt")
        subprocess.run(self.step()["words"], shell=True, cwd=self.root, capture_output=True, check=True, stdin=subprocess.DEVNULL)
        self.assertEqual(git(self.root, "show", "--name-only", "--format=", "HEAD"), "specs/INTENT-1.md")
        self.assertEqual(git(self.root, "diff", "--cached", "--name-only"), "staged.txt", "the staged file stays staged, uncommitted")

    def test_an_intent_a_person_already_agreed_to_ignores_the_patch(self):
        self.save_patch()
        self.file.write_text(INTENT.format(agreed=AGREED), encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "agree", "--trailer", f"Agreed-by: {PERSON}")
        self.assertNotIn("git apply", str(open_work(self.root)))

    def test_plain_status_shows_the_command(self):
        self.save_patch()
        shown = aidd_subprocess("status", cwd=self.root, env=hermetic_environ())
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertIn(self.step()["words"], shown.stdout)

    def test_a_path_with_other_text_gets_no_command(self):
        for path in ("specs/a b.md", "specs/$(x).md", "../INTENT-1.md", "-INTENT-1.md", "specs/a;b.md", ""):
            with self.subTest(path=path):
                self.assertEqual(saved_agreement.person_command("INTENT-1", path), "")
        self.assertIn("specs/INTENT-1.md", saved_agreement.person_command("INTENT-1", "specs/INTENT-1.md"))
        self.assertEqual(saved_agreement.person_command("not an id", "specs/INTENT-1.md"), "")


if __name__ == "__main__":
    unittest.main()
