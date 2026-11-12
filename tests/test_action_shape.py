"""`action.yml` is what every GitHub adopter runs, and actionlint cannot lint a composite action."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, SAMPLE_SPEC, git


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


CONFIG = """aidd_version: "1.0.0"
profile: solo
owners:
  approvers: [bob]
tests:
  - name: unit
    command: ["{py}", -c, print('suite ok')]
"""
# A Spec `aidd test` runs and passes: its one command is green on the head.
GOOD_SPEC = SAMPLE_SPEC.replace(
    "[python3, -m, unittest, tests.test_discount]\n      new_behavior: true", f"[{sys.executable}, -c, print('ok')]\n      new_behavior: false"
).replace('files: ["tests/test_discount.py"]', "files: []")
# Where `aidd validate` finds an error: a Task scope of `**` covers the whole repository. `aidd test` stops on it too.
BAD_SPEC = GOOD_SPEC.replace('scope: ["src/checkout/"]', 'scope: ["**"]')
# Where only `aidd validate` speaks: an agent named in `approved_by` is a warning, and `aidd test` stays green.
WARN_SPEC = GOOD_SPEC.replace(
    "route: normal", 'route: normal\nstatus: approved\napproved_at: "2026-11-01T10:00:00Z"\napproved_by: "Claude <noreply@anthropic.com>"'
)


def action_script() -> str:
    """The shell of the step that runs the tests in `action.yml`: the `run: |` block, unindented."""
    steps = (ROOT / "action.yml").read_text(encoding="utf-8").split("\nruns:", 1)[1]
    block = steps.split("      run: |\n", 1)[1].split("\n    - name:", 1)[0]
    return "\n".join(line[8:] for line in block.splitlines())


class ActionValidatesTests(unittest.TestCase):
    """A13: an adopter's CI runs `aidd validate` as aidd's own CI does, so a Spec error shows on the pull request. The
    tests' exit code stands, a validate error fails an otherwise green step, a warning never fails it, and an annotation
    is written only by aidd's own lines."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "a@example.com")
        git(self.root, "config", "user.name", "A")
        (self.root / ".aidd").mkdir()
        (self.root / ".aidd" / "config.yaml").write_text(CONFIG.replace("{py}", sys.executable), encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "base")
        git(self.root, "update-ref", "refs/remotes/origin/main", "main")
        git(self.root, "checkout", "-qb", "feat")

    def run_action(self, validate: str = "true") -> subprocess.CompletedProcess:
        env = {**os.environ, "BASE_REF": "main", "IN_PLACE": "false", "VALIDATE": validate, "PYTHONPATH": str(ROOT / "src"), "RUNNER_TEMP": self.tmp.name}
        return subprocess.run(["bash", "-c", action_script()], cwd=self.root, env=env, capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)

    def commit(self, rel: str, text: str) -> None:
        (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.root / rel).write_text(text, encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", f"add {rel}")

    def test_a_clean_repository_passes(self):
        self.commit("specs/SPEC-1.md", GOOD_SPEC)
        done = self.run_action()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotRegex(done.stdout, r"(?m)^::(error|warning)::")

    def test_an_error_in_a_spec_fails_the_step_and_shows_as_an_annotation(self):
        self.commit("specs/SPEC-1.md", BAD_SPEC)
        done = self.run_action()
        self.assertNotEqual(done.returncode, 0, done.stdout)
        self.assertRegex(done.stdout, r"(?m)^::error::specs/SPEC-1\.md")

    def test_a_warning_is_an_annotation_and_never_fails_the_step(self):
        self.commit("specs/SPEC-1.md", WARN_SPEC)
        done = self.run_action()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"(?m)^::warning::specs/SPEC-1\.md: approved_by")

    def test_validate_false_runs_the_tests_only(self):
        self.commit("specs/SPEC-1.md", WARN_SPEC)
        done = self.run_action("false")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotRegex(done.stdout, r"(?m)^::(error|warning)::")

    def test_the_tests_exit_code_stands_when_the_tests_fail(self):
        self.commit("specs/SPEC-1.md", GOOD_SPEC)
        config = self.root / ".aidd" / "config.yaml"
        config.write_text(config.read_text(encoding="utf-8").replace("print('suite ok')", "raise SystemExit(3)"), encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "red")
        done = self.run_action()
        self.assertNotEqual(done.returncode, 0, done.stdout)

    def test_only_the_error_and_warning_lines_become_annotations(self):
        # A fake interpreter, first on the PATH, gives `aidd validate` a line a pull request wrote that starts a workflow
        # command, a `%`, and a note; `aidd test` passes. Nothing but the two annotations is outside a stop-commands region.
        shim = Path(self.tmp.name) / "bin"
        shim.mkdir()
        fake = shim / "python3.15"
        fake.write_text(
            "#!/bin/bash\n"
            '[ "$1" = "-c" ] && { case "$2" in *secrets*) echo faketoken;; esac; exit 0; }\n'
            'case "$4" in validate) printf \'%s\\n\' "error: a.md: 100% bad" "::add-mask::x" "warning: b.md: odd" "note: c"; exit 1;; esac\n',
            encoding="utf-8",
        )
        fake.chmod(0o755)
        env = {
            **os.environ,
            "PATH": f"{shim}{os.pathsep}{os.environ['PATH']}",
            "BASE_REF": "main",
            "IN_PLACE": "false",
            "VALIDATE": "true",
            "RUNNER_TEMP": self.tmp.name,
        }
        done = subprocess.run(["bash", "-c", action_script()], cwd=self.root, env=env, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertEqual(
            done.stdout.splitlines(),
            [
                "::stop-commands::faketoken",
                "::faketoken::",
                "::error::a.md: 100%25 bad",
                "::stop-commands::faketoken",
                "::add-mask::x",  # plain text inside the stop region: GitHub reads no command from it, indented or not
                "::faketoken::",
                "::warning::b.md: odd",
                "::stop-commands::faketoken",
                "note: c",
                "::faketoken::",
            ],
        )

    def test_a_line_in_aidd_output_that_starts_a_workflow_command_is_never_read_as_one(self):
        """GitHub trims leading spaces before it reads a command, so indenting a line does not defuse it. A file name from the
        pull request carries a newline, and `aidd test` names it in its dirty-tree note: that line sits inside the stop region."""
        (self.root / "a\n::error::pwn").write_text("x", encoding="utf-8")
        done = self.run_action()
        lines = done.stdout.splitlines()
        stop = next(n for n, ln in enumerate(lines) if ln.startswith("::stop-commands::"))
        token = lines[stop].split("::")[-1]
        hostile = next(n for n, ln in enumerate(lines) if ln.startswith("::error::pwn"))
        resume = max(n for n, ln in enumerate(lines) if ln == f"::{token}::")
        self.assertTrue(stop < hostile < resume, (stop, hostile, resume, done.stdout))
        self.assertEqual([ln for ln in lines[:stop] if ln.startswith("::")], [], "nothing before the stop command is a command")

    def test_the_tests_run_with_require_green_so_a_spec_before_implement_fails_the_check(self):
        self.assertIn("--require-green", action_script())
        script = (ROOT / "templates" / "gitlab" / "aidd.gitlab-ci.yml").read_text(encoding="utf-8")
        self.assertIn("--require-green", script)
        self.assertIn("--require-green", (ROOT / ".github" / "workflows" / "aidd-tests.yml").read_text(encoding="utf-8"))


class GitlabTemplateValidatesTests(unittest.TestCase):
    """A13: the GitLab job runs `aidd validate` after the tests, and its exit code is the tests' when they fail, else validate's."""

    def script(self) -> str:
        text = (ROOT / "templates" / "gitlab" / "aidd.gitlab-ci.yml").read_text(encoding="utf-8")
        block = text.split("  script:\n", 1)[1].split("    - |\n", 1)[1].split("\n  artifacts:", 1)[0]
        return "\n".join(line[6:] for line in block.splitlines())

    def test_the_exit_code_of_each_pair_of_results(self):
        for tests, validate, want in ((0, 0, 0), (0, 1, 1), (0, 2, 2), (1, 0, 1), (3, 1, 3), (2, 0, 2)):
            with self.subTest(tests=tests, validate=validate):
                prelude = f'aidd() {{ case "$1" in test) return {tests};; validate) return {validate};; esac; }}\nCI_MERGE_REQUEST_TARGET_BRANCH_NAME=main\n'
                done = subprocess.run(["bash", "-c", prelude + self.script()], capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
                self.assertEqual(done.returncode, want, done.stderr)

    # The job keeps each test command's full output in its artifact unless `AIDD_UPLOAD_LOGS` is `false`, as the action's `upload-logs` does.

    def run_job(self, setting: str | None) -> tuple[bool, bool]:
        """(logs kept, evidence.json kept) after the job's script, with the variable set to `setting` (None: the template's own default)."""
        text = (ROOT / "templates" / "gitlab" / "aidd.gitlab-ci.yml").read_text(encoding="utf-8")
        default = re.search(r'(?m)^    AIDD_UPLOAD_LOGS: "([^"]*)"', text).group(1)
        with tempfile.TemporaryDirectory() as folder:
            evidence = Path(folder) / ".aidd" / "evidence"
            (evidence / "logs").mkdir(parents=True)
            (evidence / "logs" / "green-unit.log").write_text("output\n", encoding="utf-8")
            (evidence / "evidence.json").write_text("{}\n", encoding="utf-8")
            prelude = f"aidd() {{ return 0; }}\nCI_MERGE_REQUEST_TARGET_BRANCH_NAME=main\nAIDD_UPLOAD_LOGS={setting or default}\n"
            done = subprocess.run(["bash", "-c", prelude + self.script()], cwd=folder, capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
            self.assertEqual(done.returncode, 0, done.stderr)
            return (evidence / "logs").exists(), (evidence / "evidence.json").exists()

    def test_logs_stay_by_default_and_go_when_the_variable_is_false(self):
        for setting, want in ((None, (True, True)), ("true", (True, True)), ("false", (False, True))):
            with self.subTest(setting=setting):
                self.assertEqual(self.run_job(setting), want)


if __name__ == "__main__":
    unittest.main()
