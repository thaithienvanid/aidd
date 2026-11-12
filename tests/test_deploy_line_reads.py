"""The delegate check reads a workflow's `run:` lines for the deploy actions only, and starts no git process to do it.

Invariant: a command that writes a file adds only `code.edit` steps to `risk.command_level`'s answer, and the delegate check counts
only the actions in `diff_signals.DEPLOYING`. So `deploy_line` and `deploying_workflows` give the answer they gave when the write
check ran for every line ("old" below: `command_level`, which adds the write steps), for every workflow, and they read no file
through git for it. The cost is counted in git calls, never timed.
"""

from __future__ import annotations

import itertools
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import helpers

from aidd import risk
from aidd.delegation import diff_signals
from aidd.risk import edit_free_actions
from aidd.kernel import git as kernel_git

RS = risk.rule_set(None)
REAL = risk.command_level


def old_actions_without_edits(rs, line, *, cwd=None):
    """The actions of a line as the delegate check read them before: `command_level`, which also adds the steps for the files it writes."""
    return REAL(rs, line, cwd=cwd)["actions"]


def before_the_change():
    """The delegate check's own view of `risk` while it reads a workflow, with the write check on for every line."""
    return mock.patch.object(diff_signals, "risk", types.SimpleNamespace(actions_without_edits=old_actions_without_edits, command_level=REAL))


def deploy_lines_old(text: str) -> int | None:
    with before_the_change():
        return diff_signals.deploy_line(text, RS)


WRITERS = (
    "",
    "echo hi > out.txt && ",
    "tee x < in | ",
    "cp a b && ",
    "sed -i s/a/b/ .github/workflows/ci.yml; ",
    "cat a >> .claude/settings.json && ",
    "echo x > $FILE && ",
)
COMMANDS = ("terraform apply", "npm publish", "gh release create v1", "npm run deploy", "make deploy", "echo done", "pytest -q", "git push origin main")
SUFFIXES = ("", " > log.txt", " 2>&1 | tee run.log")


def workflow(run: str) -> str:
    return f"on: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - run: {run}\n"


def block_workflow(*lines: str) -> str:
    body = "".join(f"          {line}\n" for line in lines)
    return f"on: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - run: |\n{body}"


class TheDeployLineIsTheOneTheWriteCheckGaveTests(unittest.TestCase):
    def test_every_workflow_of_a_generated_set_has_the_line_it_had(self):
        texts = [workflow(f"{w}{c}{s}") for w, c, s in itertools.product(WRITERS, COMMANDS, SUFFIXES)]
        texts += [block_workflow(f"{w}{c}{s}", "echo after > note.txt") for w, c, s in itertools.product(WRITERS[:4], COMMANDS[:4], SUFFIXES[:2])]
        found = [deploy_lines_old(text) for text in texts]
        self.assertTrue(any(f is not None for f in found), "the control: some workflow deploys")
        self.assertTrue(any(f is None for f in found), "the control: some workflow does not")
        for text, expected in zip(texts, found, strict=True):
            with self.subTest(run=text.splitlines()[-1][:80]):
                self.assertEqual(diff_signals.deploy_line(text, RS), expected)

    def test_the_workflows_the_repository_ships_have_the_line_they_had(self):
        paths = sorted([*Path(helpers.ROOT, ".github", "workflows").glob("*.y*ml"), *Path(helpers.ROOT, "templates").rglob("*.y*ml")])
        self.assertTrue(paths, "the control: the repository ships workflows")
        for path in paths:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertEqual(diff_signals.deploy_line(text, RS), deploy_lines_old(text))

    def test_a_write_step_is_never_a_deploying_action(self):
        """The ground of the change: every step the write check adds is a `code.edit`, which the delegate check does not count."""
        self.assertNotIn("code.edit", diff_signals.DEPLOYING)
        for w, c, s in itertools.product(WRITERS, COMMANDS, SUFFIXES):
            line = f"{w}{c}{s}"
            with self.subTest(line=line):
                with_writes = REAL(RS, line, cwd=None)["actions"]
                self.assertEqual([a for a in with_writes if a["action"] != "code.edit"], risk.actions_without_edits(RS, line, cwd=None))


class AnAnswerWithoutTheWriteStepsDoesNotLeakIntoTheNextTests(unittest.TestCase):
    def test_the_next_answer_has_its_write_steps_again(self):
        line = "echo x > .claude/settings.json"
        with tempfile.TemporaryDirectory() as tmp:
            helpers.git(tmp, "init", "-q", "-b", "main")
            edits = lambda actions: [a for a in actions if a["action"] == "code.edit"]  # noqa: E731
            self.assertTrue(edits(REAL(RS, line, cwd=tmp)["actions"]), "the control: this command is an edit of a protected file")
            self.assertEqual(edits(risk.actions_without_edits(RS, line, cwd=tmp)), [])
            self.assertTrue(edits(REAL(RS, line, cwd=tmp)["actions"]))
            with mock.patch.object(edit_free_actions, "command_level", side_effect=RuntimeError("stopped")), self.assertRaises(RuntimeError):
                risk.actions_without_edits(RS, line, cwd=tmp)
            self.assertTrue(edits(REAL(RS, line, cwd=tmp)["actions"]), "a call that failed leaves the write check on")


class TheWorkflowsAtACommitAreReadAsTheyWereTests(unittest.TestCase):
    FILES = {
        ".github/workflows/ship.yml": workflow("echo built > dist/out.txt && terraform apply"),
        ".github/workflows/test.yml": workflow("pytest -q > report.txt"),
        ".github/workflows/log.yml": workflow("npm publish 2>&1 | tee publish.log"),
        ".github/workflows/env.yml": "on: push\njobs:\n  go:\n    environment: production\n    steps:\n      - run: echo ok > ok.txt\n",
        ".github/workflows/notes.yml": block_workflow("echo one > one.txt", "cp one.txt two.txt", "echo done"),
    }

    def test_the_workflows_that_deploy_are_the_ones_that_did(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            helpers.git(root, "init", "-q", "-b", "main")
            for rel, text in self.FILES.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(text, encoding="utf-8")
            helpers.git(root, "add", "-A")
            helpers.git(root, "-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-qm", "workflows")
            tip = helpers.git(root, "rev-parse", "HEAD")
            new = diff_signals.deploying_workflows(RS, tip, "main", str(root))
            with before_the_change():
                old = diff_signals.deploying_workflows(RS, tip, "main", str(root))
        self.assertEqual(new, old)
        self.assertEqual(sorted(path.split(":")[0] for path in new), [".github/workflows/env.yml", ".github/workflows/log.yml", ".github/workflows/ship.yml"])


class TheDeployLineStartsNoGitProcessForTheWriteCheckTests(unittest.TestCase):
    def git_calls(self, text: str, *, old: bool) -> int:
        with mock.patch.object(kernel_git, "_git", wraps=kernel_git._git) as calls:
            if old:
                deploy_lines_old(text)
            else:
                diff_signals.deploy_line(text, RS)
        return calls.call_count

    def test_fifty_lines_that_write_a_file_cost_no_git_call(self):
        text = block_workflow(*[f"echo {n} > out{n}.txt && tee log{n}.txt < in" for n in range(50)])
        self.assertGreater(self.git_calls(text, old=True), 0, "the control: the write check does start git")
        self.assertEqual(self.git_calls(text, old=False), 0)


if __name__ == "__main__":
    unittest.main()
