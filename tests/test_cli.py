import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT

from aidd import __version__, cli, evals


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = cli.main(list(argv))
    return code, out.getvalue()


class InitRefTests(unittest.TestCase):
    def test_a_bad_ref_is_a_usage_error_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            code, out = run("init", d, "--ref", "main; rm -rf /", "--approvers", "@org/leads")
            self.assertEqual(code, 2, out)
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_a_commit_ref_pins_the_generated_workflows(self):
        sha = "a" * 40
        with tempfile.TemporaryDirectory() as d:
            code, out = run("init", d, "--ref", sha, "--approvers", "@org/leads", "--no-skill")
            self.assertEqual(code, 0, out)
            gate = (Path(d) / ".github/workflows/aidd-gate.yml").read_text(encoding="utf-8")
            self.assertIn(f"gate.yml@{sha} # aidd {sha[:12]}\n", gate)  # not a release commit: no release label
            self.assertNotRegex(gate, r"@v\d+\.\d+\.\d+\s*$")


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
                self.assertEqual(run("proposal", "matrix", "nope.md")[0], 2)
                Path("bad.md").write_text("not a proposal\n", encoding="utf-8")
                self.assertEqual(run("proposal", "matrix", "bad.md")[0], 2)
                env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_CHILD_SESSION", "AI_AGENT", "AIDD_AGENT")}
                with mock.patch.dict(os.environ, env, clear=True):
                    self.assertEqual(run("approve", "spec")[0], 2)  # no Spec named
                    self.assertEqual(run("approve", "spec", "specs/NOPE.md")[0], 2)  # no such file
                    Path("specs").mkdir()
                    Path("specs/SPEC-1.md").write_text("+++\n+++\n", encoding="utf-8")
                    self.assertEqual(run("approve", "spec", "specs/SPEC-1.md")[0], 1)  # there, but not committed: a failed check
            finally:
                os.chdir(cwd)


class CliTests(unittest.TestCase):
    def test_version_and_help(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as exit_:
            cli.main(["--version"])
        self.assertEqual(exit_.exception.code, 0)
        self.assertEqual(out.getvalue().split(), ["aidd", __version__])

    def test_validate_example_specs(self):
        specs = sorted(str(p) for p in (ROOT / "examples/_specs").glob("*.md"))
        self.assertGreaterEqual(len(specs), 5, "the glob found no example Specs, so validate would check nothing")
        code, out = run("validate", *specs)
        self.assertEqual(code, 0, out)

    def test_eval_examples(self):
        code, out = run("eval", "examples")
        self.assertEqual(code, 0, out)

    def test_gate_context_file_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            for case, want in (("02-normal-feature", 0), ("03-normal-waiting", 3), ("08-scope-creep", 1)):
                ctx, _ = evals.load_example(ROOT / "examples" / case)
                p = Path(d) / f"{case}.json"
                p.write_text(json.dumps(ctx), encoding="utf-8")
                code, out = run("gate", "--context", str(p), "--events", str(Path(d) / "events.jsonl"))
                self.assertEqual(code, want, out)
            code, out = run("metrics", str(Path(d) / "events.jsonl"))
            self.assertEqual(code, 0)
            self.assertIn("Final decisions", out)

    def test_planned_paths_with_globs_and_folders(self):
        from aidd import config, rules

        cfg = config.load_text('aidd_version = "1.0.0"\nprofile = "team"\n[owners]\napprovers = ["@x"]\n')
        self.assertEqual(rules.assess_paths(cfg, ["src/auth/", "docs/x.md"]).required_route, "major")
        self.assertEqual(rules.assess_paths(cfg, ["docs/**"]).required_route, "minor")
        self.assertEqual(rules.assess_paths(cfg, ["src/a.py"], dimensions=["privacy"]).required_route, "major")
        self.assertEqual(rules.assess_paths(cfg, ["src/a.py"], irreversible=True).required_route, "major")

    def test_eval_routing_scoring_with_a_fake_agent(self):
        with tempfile.TemporaryDirectory() as d:
            agent = Path(d) / "agent.py"
            agent.write_text('import sys\nsys.stdin.read()\nprint("thinking...")\nprint(\'{"route": "normal", "reason": "fake"}\')\n', encoding="utf-8")
            # The agent always answers normal, so its accuracy is the share of scenarios whose route is normal.
            scenarios = evals.load_scenarios(ROOT / "evals" / "routing")
            accuracy = sum(sc["expected"]["route"] == "normal" for sc in scenarios) / len(scenarios)
            self.assertTrue(0 < accuracy < 1, accuracy)
            cmd = f"{sys.executable} {agent}"
            code, out = run("eval", "routing", "--cmd", cmd, "--min-accuracy", f"{accuracy - 0.001:.4f}")
            self.assertEqual(code, 0, out)
            self.assertIn(f"accuracy {accuracy:.1%}", out)  # the one check on the formatted line
            self.assertEqual(run("eval", "routing", "--cmd", cmd, "--min-accuracy", f"{accuracy + 0.001:.4f}")[0], 1)


if __name__ == "__main__":
    unittest.main()
