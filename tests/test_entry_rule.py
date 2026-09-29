"""The entry rule without `aidd assess`: `aidd next`, `aidd new spec --paths`, `aidd change`, and the local gate each
show the computed route, its lane, and why."""

import contextlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import git

from aidd import cli, model, repo


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = cli.main(list(argv))
    return code, out.getvalue()


@unittest.skipUnless(shutil.which("git"), "git is required")
class EntryRuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)  # after a test's chdir is undone: Windows cannot remove the working directory
        self.root = Path(self.tmp.name)
        git(self.root, "init", "-q", "-b", "main")
        repo.init(self.root, profile="team", ci="none", links=[], approvers=["@lead"], harnesses=[], test=["python3", "-c", "pass"])
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "day 0")
        git(self.root, "switch", "-qc", "work")
        self.enterContext(contextlib.chdir(self.root))

    def spec(self, sid):
        return model.split_front_matter((self.root / "specs" / f"{sid}.md").read_text(encoding="utf-8"), sid)[0]

    def test_assess_is_gone(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            cli.main(["assess"])

    def test_fast_lane_paths_need_no_spec_unless_forced(self):
        code, out = run("new", "spec", "SPEC-1", "--title", "t", "--paths", "app/discount.py")
        self.assertEqual(code, 0, out)
        self.assertIn("route: the minimum for these paths is minor (fast lane)", out)
        self.assertIn("no Spec needed", out)
        self.assertIn("aidd change", out)
        self.assertFalse((self.root / "specs" / "SPEC-1.md").exists())
        code, out = run("new", "spec", "SPEC-1", "--title", "t", "--paths", "app/discount.py", "--force")
        self.assertEqual(code, 0, out)
        data = self.spec("SPEC-1")
        self.assertEqual((data["route"], data["tasks"][0]["scope"]), ("normal", ["app/discount.py"]))

    def test_the_computed_route_and_scope_are_written(self):
        code, out = run("new", "spec", "SPEC-2", "--title", "t", "--paths", "db/migrations/", "src/models/order.py", "--type", "feat")
        self.assertEqual(code, 0, out)
        self.assertIn("major (spec lane)", out)
        self.assertIn("rule baseline:", out)  # the reason lines
        data = self.spec("SPEC-2")
        self.assertEqual((data["route"], data["tasks"][0]["scope"]), ("major", ["db/migrations/", "src/models/order.py"]))
        self.assertIn("observe", data)  # major carries its observe block
        code, out = run("new", "spec", "SPEC-3", "--title", "t", "--paths", "src/a.py", "--dimension", "privacy", "--irreversible", "--route", "normal")
        self.assertEqual(code, 0, out)
        self.assertIn("never below the computed minimum", out)
        data = self.spec("SPEC-3")
        self.assertEqual((data["route"], data["risk"]["dimensions"], data["risk"]["reversible"]), ("major", ["privacy"], False))
        code, out = run("new", "spec", "SPEC-4", "--title", "t", "--paths", "src/a.py", "src/b.py", "--dimension", "availability", "--route", "major")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.spec("SPEC-4")["route"], "major")  # a higher --route stands
        self.assertEqual(run("new", "epic", "EPIC-1", "--title", "t", "--paths", "src/a.py")[0], 2)

    def test_change_prints_the_reasons(self):
        (self.root / "docs").mkdir()
        (self.root / "docs" / "a.md").write_text("x\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "docs")
        code, out = run("change")
        self.assertEqual(code, 0, out)
        self.assertIn("# The diff's minimum route is minor (fast lane), because:", out)
        self.assertIn("#   - no risk rule, protected path, or declared risk raised it", out)
        (self.root / ".github" / "workflows").mkdir(parents=True)
        (self.root / ".github" / "workflows" / "ci.yml").write_text("on: push\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "ci")
        code, out = run("change")
        self.assertIn("major (spec lane)", out)
        self.assertIn("#   - protected path matched .github/workflows/ci.yml -> at least major", out)
        self.assertIn("aidd new spec <ID>", out)
        self.assertIn("--paths .github/workflows/ci.yml docs/a.md", out)

    def test_a_local_gate_prints_the_route_it_computed(self):
        (self.root / "docs").mkdir()
        (self.root / "docs" / "a.md").write_text("x\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "docs")
        body = self.root.parent / f"{self.root.name}-body.md"
        body.write_text('```toml aidd\nroute = "minor"\ntype = "docs"\nscope = ["docs/a.md"]\nassisted_by = []\n```\n', encoding="utf-8")
        _, out = run("gate", "--base", "main", "--body-file", str(body), "--no-policy")
        self.assertIn("computed route minor (fast lane) from the diff, because:", out)
        self.assertIn("    - no risk rule, protected path, or declared risk raised it", out)

    def test_next_shows_the_route_for_the_branch(self):
        (self.root / "db" / "migrations").mkdir(parents=True)
        (self.root / "db" / "migrations" / "1.sql").write_text("select 1;\n", encoding="utf-8")
        code, out = run("next")
        self.assertEqual(code, 0, out)
        self.assertIn("needs route major (spec lane)", out)
        self.assertIn("aidd new spec <ID>", out)


if __name__ == "__main__":
    unittest.main()
