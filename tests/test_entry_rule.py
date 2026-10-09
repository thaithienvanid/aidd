"""The entry check: `aidd assess` (for a branch, or `--paths` before any code), `aidd new spec --paths`, `aidd describe`,
and the local gate each show the route, its lane, and why. A change's route is the higher of what it touches needs and
what it declares."""

import contextlib
import io
import json
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
class EntryCheckTests(unittest.TestCase):
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

    def test_assess_previews_the_route_of_planned_paths_before_any_code(self):
        code, out = run("assess", "--paths", "app/discount.py")
        self.assertEqual(code, 0, out)
        self.assertTrue(out.startswith("Route: minor (fast lane), needed by the planned paths (1 path)"), out)
        self.assertIn("Implement and Verify, repeated until green", out)
        self.assertIn("aidd describe", out)
        code, out = run("assess", "--paths", "src/a.py", "--dimension", "privacy", "--irreversible")
        self.assertIn("Route: major (spec lane)", out)
        self.assertIn('aidd new spec <ID> --title "..." --paths src/a.py', out)
        self.assertEqual(sorted(p.name for p in (self.root / "specs").glob("*.md")), ["README.md"])  # a preview writes nothing
        self.assertEqual(run("assess", "--type", "fix")[0], 2)  # --type describes planned paths

    def test_fast_lane_paths_need_no_spec_unless_forced(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["new", "spec", "SPEC-1", "--title", "t", "--paths", "app/discount.py"])
        # Nothing is written, so the exit says so: a script that goes on to edit the Spec must not think it exists.
        self.assertEqual(code, 1, out.getvalue() + err.getvalue())
        self.assertIn("route: the minimum for these paths is minor (fast lane)", out.getvalue())
        self.assertIn("no Spec written", err.getvalue())
        self.assertIn("`--force` writes one", err.getvalue())
        self.assertIn("aidd describe", err.getvalue())
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

    def test_describe_prints_the_reasons(self):
        (self.root / "docs").mkdir()
        (self.root / "docs" / "a.md").write_text("x\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "docs")
        code, out = run("describe")
        self.assertEqual(code, 0, out)
        self.assertIn("# The diff's minimum route is minor (fast lane), because:", out)
        self.assertIn("#   - no risk rule, protected path, or declared risk raised it", out)
        (self.root / ".github" / "workflows").mkdir(parents=True)
        (self.root / ".github" / "workflows" / "ci.yml").write_text("on: push\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "ci")
        code, out = run("describe")
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

    def test_assess_shows_the_route_for_the_branch(self):
        (self.root / "db" / "migrations").mkdir(parents=True)
        (self.root / "db" / "migrations" / "1.sql").write_text("select 1;\n", encoding="utf-8")
        code, out = run("assess")
        self.assertEqual(code, 0, out)
        self.assertTrue(out.startswith("Route: major (spec lane), needed by this branch's diff against main (1 path)"), out)
        self.assertIn("  - rule baseline:migrations matched db/migrations/1.sql", out)
        self.assertIn("aidd new spec <ID>", out)

    def test_the_route_is_the_higher_of_the_declared_and_the_computed(self):
        run("new", "spec", "SPEC-5", "--title", "t", "--route", "major", "--paths", "docs/a.md", "--force")
        (self.root / "docs").mkdir()
        (self.root / "docs" / "a.md").write_text("x\n", encoding="utf-8")
        code, out = run("assess")
        self.assertEqual(code, 0, out)
        self.assertTrue(out.startswith("Route: major (spec lane), set by SPEC-5; the diff alone needs "), out)
        self.assertIn("SPEC-5", out.split("Next for this change:", 1)[1])  # the Spec's own step, not the lane's
        answer = json.loads(run("assess", "--json")[1])
        self.assertEqual((answer["route"]["route"], answer["route"]["declared"]), ("major", {"route": "major", "by": "SPEC-5"}))
        # A change declared below what it touches is raised: the gate enforces the higher of the two.
        data = self.spec("SPEC-5")
        text = (self.root / "specs" / "SPEC-5.md").read_text(encoding="utf-8").replace('route = "major"', 'route = "normal"', 1)
        (self.root / "specs" / "SPEC-5.md").write_text(text, encoding="utf-8")
        (self.root / ".github" / "workflows").mkdir(parents=True)
        (self.root / ".github" / "workflows" / "ci.yml").write_text("on: push\n", encoding="utf-8")
        _, out = run("assess")
        self.assertTrue(out.startswith("Route: major (spec lane), needed by the diff; SPEC-5 declares normal, and the gate enforces the higher"), out)
        self.assertEqual(data["route"], "major")

    def test_next_is_no_command(self):
        # 1.0.0 is the first release: the pre-release name `next` is gone, not kept as an alias.
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as stop:
            cli.main(["next"])
        self.assertEqual(stop.exception.code, 2)
        self.assertIn("invalid choice: 'next'", err.getvalue())
        listed = [line.split()[0] for line in cli.build_parser().format_help().splitlines() if line.startswith("  ") and line.split()]
        self.assertIn("assess", listed)


if __name__ == "__main__":
    unittest.main()
