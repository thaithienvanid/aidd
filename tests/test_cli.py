import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, git

from aidd import __version__
from aidd.evals import suites
from aidd.cli import app


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = app.main(list(argv))
    return code, out.getvalue()


class InitRefTests(unittest.TestCase):
    def test_a_bad_ref_is_a_usage_error_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q", "-b", "main")
            code, out = run("init", d, "--ref", "main; rm -rf /", "--approvers", "@org/leads")
            self.assertEqual(code, 2, out)
            self.assertIn("--ref", out)
            self.assertEqual([p.name for p in Path(d).iterdir()], [".git"])

    def test_a_commit_ref_pins_the_generated_workflows(self):
        sha = "a" * 40
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q", "-b", "main")
            code, out = run("init", d, "--ref", sha, "--approvers", "@org/leads", "--no-skill", "--ci", "github")
            self.assertEqual(code, 0, out)
            tests = (Path(d) / ".github/workflows/aidd-tests.yml").read_text(encoding="utf-8")
            self.assertIn(f"aidd@{sha} # aidd {sha[:12]}\n", tests)  # not a release commit: no release label
            self.assertNotRegex(tests, r"@v\d+\.\d+\.\d+\s*$")


class ExitCodeTests(unittest.TestCase):
    """Bad input or a missing file is 2 (usage); a check that ran and failed is 1."""

    def test_bad_input_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as d:
            missing = str(Path(d) / "nope")
            self.assertEqual(run("init", "--dry-run", missing)[0], 2)
            self.assertEqual(run("init", missing, "--approvers", "@a")[0], 2)
            self.assertFalse(Path(missing).exists())
            cwd = os.getcwd()
            os.chdir(d)
            try:
                import subprocess

                subprocess.run(["git", "init", "-q"], check=True)
                self.assertEqual(run("validate", "specs/NOPE.md")[0], 2)  # no such file
                Path("specs").mkdir()
                Path("specs/SPEC-1.md").write_text("---\n---\n", encoding="utf-8")
                self.assertEqual(run("validate", "specs/SPEC-1.md")[0], 1)  # there, but not valid: a failed check
            finally:
                os.chdir(cwd)


class CliTests(unittest.TestCase):
    def test_version_and_help(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as exit_:
            app.main(["--version"])
        self.assertEqual(exit_.exception.code, 0)
        self.assertEqual(out.getvalue().split(), ["aidd", __version__])

    def test_planned_paths_with_globs_and_folders(self):
        from aidd import config
        from aidd import risk

        cfg = config.load_text('aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@x"]\n')
        self.assertEqual(risk.advice(cfg, ["src/auth/", "docs/x.md"])["route"], "major")
        self.assertEqual(risk.advice(cfg, ["docs/**"])["route"], "minor")
        self.assertEqual(risk.advice(cfg, ["src/a.py"], declared=risk.DeclaredRisk(irreversible=True))["route"], "major")

    def test_eval_routing_scoring_with_a_fake_agent(self):
        with tempfile.TemporaryDirectory() as d:
            agent = Path(d) / "agent.py"
            agent.write_text('import sys\nsys.stdin.read()\nprint("thinking...")\nprint(\'{"route": "normal", "reason": "fake"}\')\n', encoding="utf-8")
            # The agent always answers normal with a reason that names nothing, so its accuracy is the share of scenarios
            # whose route is normal and that ask nothing of the reason.
            scenarios = suites.load_scenarios(ROOT / "evals" / "routing")
            accuracy = sum(sc["expected"]["route"] == "normal" and not sc["expected"].get("reason_any") for sc in scenarios) / len(scenarios)
            self.assertTrue(0 < accuracy < 1, accuracy)
            cmd = f"{sys.executable} {agent}"
            code, out = run("eval", "routing", "--agent-command", cmd, "--min-accuracy", f"{accuracy - 0.001:.4f}")
            self.assertEqual(code, 0, out)
            self.assertIn(f"accuracy {accuracy:.1%}", out)  # the one check on the formatted line
            self.assertEqual(run("eval", "routing", "--agent-command", cmd, "--min-accuracy", f"{accuracy + 0.001:.4f}")[0], 1)


if __name__ == "__main__":
    unittest.main()
