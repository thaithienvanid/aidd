"""`action.yml` is what every GitHub adopter runs, and actionlint cannot lint a composite action."""

from __future__ import annotations

import re
import unittest

from helpers import ROOT


class CompositeActionShapeTests(unittest.TestCase):
    """`action.yml` is what every GitHub adopter runs, and actionlint cannot lint a composite action.

    There is no YAML parser available — the runtime has no dependencies — so these are textual
    assertions on a small, stable file, the same approach `tests/test_version.py` already takes for
    its action pins. Each one fails loudly rather than passing vacuously if the file is restructured.
    """

    def setUp(self):
        self.text = (ROOT / "action.yml").read_text(encoding="utf-8")
        self.assertIn("using: composite", self.text, "action.yml is no longer a composite action")

    def test_every_input_is_documented_and_has_a_default(self):
        block = self.text.split("\ninputs:", 1)[1].split("\nruns:", 1)[0]
        names = re.findall(r"(?m)^  ([a-z][a-z0-9-]*):\s*$", block)
        self.assertGreaterEqual(len(names), 3, f"inputs block changed shape: {names}")
        for name in names:
            spec = block.split(f"\n  {name}:", 1)[1]
            spec = spec[: re.search(r"(?m)^  [a-z]", spec).start()] if re.search(r"(?m)^  [a-z]", spec) else spec
            self.assertIn("description:", spec, f"input {name!r} has no description")
            self.assertIn("default:", spec, f"input {name!r} has no default, so every caller must know it")

    def test_every_used_action_is_pinned_by_commit_sha(self):
        uses = re.findall(r"(?m)^\s*-?\s*uses:\s*(\S+)", self.text)
        self.assertTrue(uses, "action.yml uses no other action; this assertion is stale")
        for u in uses:
            self.assertRegex(u, r"@[0-9a-f]{40}", f"not pinned by SHA: {u}")

    def test_every_run_step_declares_a_shell(self):
        steps = self.text.split("\nruns:", 1)[1]
        runs = re.findall(r"(?m)^\s*- run:", steps) + re.findall(r"(?m)^\s*run:", steps)
        shells = re.findall(r"(?m)^\s*shell:", steps)
        self.assertTrue(runs, "action.yml has no run step; this assertion is stale")
        self.assertEqual(len(shells), len(runs), f"{len(runs)} run step(s) but {len(shells)} shell declaration(s)")

    def test_the_interpreter_cannot_be_shadowed_by_the_pull_request_checkout(self):
        # `python -m` puts the CWD first on sys.path, ahead of PYTHONPATH, and in this action the CWD
        # is the pull request's own checkout. `-P` is what makes the comment in action.yml true.
        self.assertIn("-P -m aidd", self.text)
        self.assertNotRegex(self.text, r"py\"\s+-m aidd", "a -m aidd invocation without -P lets the PR checkout shadow the module")
        self.assertRegex(self.text, r"python3\.1[1-9]", "the interpreter discovery should prefer a supported Python")

    def test_the_head_binding_check_survives(self):
        # The action refuses to run when the checkout is not the head the gate will read.
        self.assertIn("HEAD_SHA", self.text)
        self.assertIn("GITHUB_EVENT_PATH", self.text)


class CiWorkflowShapeTests(unittest.TestCase):
    """The ci workflow: `ci passed` waits on every job, and a pull request runs few of them. Textual, as above."""

    def setUp(self):
        self.text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        body = self.text.split("\njobs:\n", 1)[1]
        self.jobs = {}
        for name, spec in zip(re.findall(r"(?m)^  ([a-z][a-z0-9-]*):\s*$", body), re.split(r"(?m)^  [a-z][a-z0-9-]*:\s*$", body)[1:], strict=True):
            self.jobs[name] = spec
        self.assertIn("ci-passed", self.jobs, "the summary job moved")

    def test_ci_passed_waits_on_every_other_job(self):
        needs = re.search(r"needs: \[([^\]]*)\]", self.jobs["ci-passed"]).group(1)
        self.assertEqual(sorted(x.strip() for x in needs.split(",")), sorted(j for j in self.jobs if j != "ci-passed"))
        self.assertIn("name: ci passed", self.jobs["ci-passed"])
        self.assertIn("if: always()", self.jobs["ci-passed"])

    def test_a_pull_request_runs_the_checks_and_the_tests_only(self):
        on_prs = sorted(j for j, spec in self.jobs.items() if "if: github.event_name != 'pull_request'" not in spec.split("steps:", 1)[0])
        self.assertEqual(on_prs, ["checks", "ci-passed", "test"])
        # The test job runs the suite on the oldest supported Python (aidd-tests runs the newest on every pull request)
        # and installs the wheel on both. It never skips: about sixty test modules read Markdown, so no change is
        # documentation only.
        self.assertEqual(re.findall(r"python3\.\d+ -m unittest discover -s tests", self.jobs["test"]), ["python3.11 -m unittest discover -s tests"])
        self.assertIn("for py in python3.11 python3.14; do", self.jobs["test"])
        self.assertNotIn("steps.scope.outputs.run", self.jobs["test"])
        self.assertNotIn("\\.md$", self.jobs["test"])
        self.assertIn('python-version: "3.14"', (ROOT / ".github" / "workflows" / "aidd-tests.yml").read_text(encoding="utf-8"))
        # On main, the matrix covers Linux 3.14, which the test job no longer runs.
        self.assertNotIn('{ os: ubuntu-latest, python: "3.14" }', self.jobs["matrix"])
        # No job installs aidd from the source tree, which would fetch an unpinned build backend.
        self.assertNotIn("pip install -e", self.text)
        self.assertNotIn("pip install -e", (ROOT / ".github" / "workflows" / "evals.yml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
