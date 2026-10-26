"""`aidd new spec "Title"`: the title in place of the id, and the next free id, counted on every local branch."""

import contextlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import git

from aidd.cli import app
from aidd.setup import adoption
from aidd.workitems import spec_file


def aidd(root: Path, *argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.chdir(root), contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = app.main(list(argv))
    return code, out.getvalue()


@unittest.skipUnless(shutil.which("git"), "git is required")
class NewIdTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        git(self.root, "init", "-q", "-b", "main")
        adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=[]))
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "chore: adopt aidd")

    def test_a_title_alone_takes_the_next_id(self):
        code, out = aidd(self.root, "new", "spec", "Apply a percentage discount", "--force")
        self.assertEqual(code, 0, out)
        self.assertIn("specs/SPEC-1.md", out)
        self.assertIn("title: Apply a percentage discount", (self.root / "specs" / "SPEC-1.md").read_text(encoding="utf-8"))
        code, out = aidd(self.root, "new", "epic", "Cut repeated work")
        self.assertEqual(code, 0, out)
        self.assertIn("specs/EPIC-1.md", out)
        code, out = aidd(self.root, "new", "proposal", "Rebuild the booking app", "--audience", "client", "--addressee", "Clinic board")
        self.assertEqual(code, 0, out)
        self.assertIn("proposals/PROP-1/proposal.md", out)

    def test_an_id_given_is_kept_and_the_next_one_follows_it(self):
        self.assertEqual(aidd(self.root, "new", "spec", "SPEC-7", "--title", "Seven", "--force")[0], 0)
        code, out = aidd(self.root, "new", "spec", "Eight", "--force")
        self.assertEqual(code, 0, out)
        self.assertIn("specs/SPEC-8.md", out)

    def test_another_branchs_ids_are_never_reused(self):
        git(self.root, "switch", "-qc", "spec/one")
        aidd(self.root, "new", "spec", "One", "--force")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "spec: SPEC-1")
        git(self.root, "switch", "-q", "main")
        self.assertEqual(spec_file.next_id(self.root, "SPEC", "specs"), "SPEC-2")
        code, out = aidd(self.root, "new", "spec", "Two", "--force")
        self.assertIn("specs/SPEC-2.md", out)


if __name__ == "__main__":
    unittest.main()
