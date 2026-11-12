"""The programs git starts for a checkout of a run of the project's tests get the test command's environment.

Invariant: a program that git starts for a checkout aidd makes in a run of the project's tests, because the repository's config
names it, gets no credential-like variable that the test command did not get. The test command is the change's own code, so it
may add a filter to the repository's config, and aidd's next checkout would run that filter.

Each program kind that such a checkout starts has a row: a smudge filter, a process filter, and the smudge filter of a submodule.
A filter that is the project's own, in the config before the run, still runs, so the red run still proves what it did.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import git

from aidd.delegation import local_run
from aidd.testing import runner as test_runner

PY = sys.executable.replace("\\", "/")
# The name is one `aidd test` removes from a test command's environment. Its value is made at run time, so no file holds it.
CREDENTIAL = "RED_RUN_TOKEN"
CONFIG = f"""aidd_version: "1.0.0"
profile: solo
owners:
  approvers: [bob]
tests:
  - name: unit
    command: ["{PY}", tools/unit.py]
"""
SPEC = f"""---
type: spec
id: SPEC-1
title: Greeting says hello
change_type: feat
route: normal
confidence: high
open_questions: []
trace_id: spec-1
rollback: Revert the PR.
risk:
  summary: Adds a greeting function.
  dimensions: []
  irreversible: false
tasks:
  - id: T1
    title: Implement greet
    scope: [app/]
tests:
  files: [checks/test_greet.py]
  commands:
    - name: greet
      command: ["{PY}", checks/test_greet.py]
      new_behavior: true
---
## Context
Tiny example.
## Acceptance
Invariant: greet() returns "hello".
"""
# Prints the file a filter shapes, then needs the code only the head has, so it fails on the base for that reason alone.
TEST = "import sys\nsys.path.insert(0, '.')\nprint('a.dat=' + open('a.dat').read().strip())\nfrom app.greet import greet\nassert greet() == 'hello'\n"
# What a program records about its environment, and what it does for git: a smudge filter hands its input back in capitals, so
# the tree it shapes shows that it ran. A process filter ends at once, and git goes on with the file as stored. A filter of kind `needs` fails without the credential, and one of kind `needsbase` fails only on the base's file.
PROBE = """import os, sys
with open(sys.argv[1], "a", encoding="utf-8") as seen:
    seen.write(sys.argv[2] + "|" + os.environ.get(sys.argv[3], "") + "\\n")
if sys.argv[2] == "process" or (sys.argv[2] == "needs" and not os.environ.get(sys.argv[3])):
    sys.exit(1)
data = sys.stdin.buffer.read()
if sys.argv[2] == "needsbase" and data == b"data\\n" and not os.environ.get(sys.argv[3]):
    sys.exit(1)
sys.stdout.buffer.write(data.upper())
"""
QUIET = "print('suite ok')\n"
GREEN = [("unit", "green", "passed"), ("greet", "green", "passed"), ("greet", "red", "failed")]


class Run:
    """A repository on `feature`, one commit past `main`, and the log of the programs git started for it."""

    def __init__(self, tmp: Path, probe: Path, number: int, value: str, folder: str = "") -> None:
        self.root, self.log, self.probe, self.value = tmp / (folder or f"repo{number}"), tmp / f"started{number}.log", probe, value
        self.out = self.root / ".aidd" / "evidence"

    def filters(self, *kinds: str) -> dict[str, str]:
        """The config that makes git run the recorder as each of these kinds of filter, named `probe`."""
        return {f"filter.probe.{k}": f'"{PY}" "{self.probe}" "{self.log}" {k} {CREDENTIAL}' for k in kinds}

    def write(self, rel: str, text: str) -> None:
        (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.root / rel).write_text(text, encoding="utf-8")

    def build(self, during: dict[str, str], submodule: Path | None = None) -> None:
        """The repository. Its own test command, `unit`, adds the settings in `during` to the repository's config."""
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "a@example.com")
        git(self.root, "config", "user.name", "A")
        plant = f"import subprocess\nfor key, value in {during!r}.items():\n    subprocess.run(['git', 'config', key, value], check=True)\n"
        self.write(".aidd/config.yaml", CONFIG)
        self.write("tools/unit.py", plant if during else QUIET)
        self.write(".gitattributes", "*.dat filter=probe\n")
        self.write("a.dat", "data\n")
        if submodule:
            git(self.root, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(submodule), "subm")
            git(self.root / "subm", "checkout", "-q", "HEAD~1")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "base")
        git(self.root, "checkout", "-qb", "feature")
        self.write("specs/SPEC-1.md", SPEC)
        self.write("checks/test_greet.py", TEST)
        self.write("app/greet.py", "def greet():\n    return 'hello'\n")
        self.write("a.dat", "data2\n")  # the base's file differs from the head's, so the checkout of the base writes it
        if submodule:
            git(self.root / "subm", "checkout", "-q", "main")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "spec and code")

    def configure(self, settings: dict[str, str], folder: str = ".") -> None:
        for key, value in settings.items():
            git(self.root / folder, "config", key, value)

    def started(self) -> list[tuple[str, str]]:
        """Each program git started, as (its kind, the credential it saw: nothing when it saw none)."""
        lines = self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []
        return sorted(tuple(line.split("|")) for line in lines)  # type: ignore[misc]

    def tests(self, **kwargs) -> dict:
        with mock.patch.dict(os.environ, {CREDENTIAL: self.value}):
            evidence, _ = test_runner.run_tests(repo=str(self.root), base="main", out_dir=str(self.out), **kwargs)
        return evidence

    def kinds(self) -> list[str]:
        return sorted({kind for kind, _ in self.started()})

    def credentials_seen(self) -> list[str]:
        return [seen for _, seen in self.started() if seen]

    def red_tree_shows(self) -> str:
        """The `a.dat` the red command printed: what the checkout of the base made of the file."""
        (log,) = self.out.glob("logs/red-*.log")
        return log.read_text(encoding="utf-8").splitlines()[0]


class Fixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp, self.count, self.value = Path(tmp.name), 0, "v" + os.urandom(8).hex()
        self.probe = self.tmp / "probe.py"
        self.probe.write_text(PROBE, encoding="utf-8")

    def run_for(self, folder: str = "") -> Run:
        self.count += 1
        return Run(self.tmp, self.probe, self.count, self.value, folder)


def answers(evidence: dict) -> list[tuple[str, str, str]]:
    return [(r["name"], r["red_green"], r["status"]) for r in evidence["results"]]


class TheBaseCheckoutRunsWithTheTestCommandsEnvironment(Fixture):
    # (filters in the config before the run, filters the test command adds, what the red command sees in a.dat, the kinds that start)
    ROWS = {
        "no filter": ((), (), "a.dat=data", []),
        "the project's own smudge filter": (("smudge",), (), "a.dat=DATA", ["smudge"]),
        "a smudge filter the test command adds": ((), ("smudge",), "a.dat=DATA", ["smudge"]),
        "a process filter the test command adds": ((), ("process",), "a.dat=data", ["process"]),
    }

    def test_each_row_proves_the_same_red_and_no_program_sees_the_credential(self):
        for name, (before, during, shows, kinds) in self.ROWS.items():
            for in_place in (False, True):
                with self.subTest(row=name, in_place=in_place):
                    run = self.run_for()
                    run.build(run.filters(*during))
                    run.configure(run.filters(*before))
                    self.assertEqual(answers(run.tests(red_in_place=in_place)), GREEN, "the same red and green answers")
                    self.assertEqual(run.red_tree_shows(), shows, "the checkout of the base still ran the filter the project needs")
                    self.assertEqual(run.kinds(), kinds, "the control: each kind that should start did")
                    self.assertEqual(run.credentials_seen(), [], "a program git started saw the credential")

    def test_a_credential_the_person_passes_by_name_reaches_the_checkout_as_it_reaches_the_test_command(self):
        run = self.run_for()
        run.build({})
        run.configure(run.filters("smudge"))
        run.tests(pass_env=[CREDENTIAL])
        self.assertEqual(set(run.credentials_seen()), {self.value})
        self.assertEqual(run.kinds(), ["smudge"], "the control: the filter ran")


class AFilterTheProjectRequiresThatNeedsACredentialStopsWithTheNextStep(Fixture):
    def needs(self, run: Run, kind: str = "needs") -> None:
        run.configure({"filter.probe.smudge": f'"{PY}" "{self.probe}" "{run.log}" {kind} {CREDENTIAL}', "filter.probe.required": "true"})

    def stop(self, run: Run, **kwargs) -> str:
        with self.assertRaises(RuntimeError) as stopped:
            run.tests(**kwargs)
        return str(stopped.exception)

    def test_only_git_saying_a_filter_failed_brings_the_note_whatever_the_folder_is_called(self):
        """A path with the word `filter` in it is no filter failure, and a real one there still gets the note."""
        quiet = self.run_for("spam-filter-service")
        quiet.build({})
        (quiet.root / ".git" / "index.lock").write_text("", encoding="utf-8")
        text = self.stop(quiet, red_in_place=True)
        self.assertIn("index.lock", text, "the control: the checkout failed for another reason")
        self.assertNotIn("--pass-env", text)
        for in_place in (False, True):
            with self.subTest(in_place=in_place):
                failing = self.run_for(f"spam-filter-service-{in_place}")
                failing.build({})
                self.needs(failing)
                self.assertIn("--pass-env", self.stop(failing, red_in_place=in_place))

    def test_a_branch_that_is_unsafe_to_print_is_restored_through_the_head_commit(self):
        run = self.run_for()
        run.build({})
        git(run.root, "branch", "-m", "feature", "it's")
        self.needs(run)
        head = git(run.root, "rev-parse", "HEAD")
        self.assertIn(f"git checkout --force {head}", self.stop(run, red_in_place=True))

    def test_a_branch_named_like_an_option_is_checked_out_again_as_the_branch(self):
        run = self.run_for()
        run.build({})
        git(run.root, "update-ref", "refs/heads/-x", "HEAD")
        git(run.root, "symbolic-ref", "HEAD", "refs/heads/-x")
        self.assertEqual(answers(run.tests(red_in_place=True)), GREEN)
        self.assertEqual(git(run.root, "symbolic-ref", "HEAD"), "refs/heads/-x")

    def test_the_delegate_checks_reason_leads_with_the_cause_and_the_next_step(self):
        """Its reason is cut at 300 characters, so the cause comes first and git's long filter text is what the cut removes."""
        for kind in ("needs", "needsbase"):  # the head's checkout fails, then the base's
            with self.subTest(fails_on=kind):
                run = self.run_for()
                run.build({})
                self.needs(run, kind)
                head, base = git(run.root, "rev-parse", "HEAD"), git(run.root, "rev-parse", "main")
                with mock.patch.dict(os.environ, {CREDENTIAL: self.value}):
                    evidence, why = local_run.run_on_head(str(run.root), head, base)
                self.assertIsNone(evidence)
                self.assertIn("--pass-env", why)
                self.assertLessEqual(len(why), 300)

    def test_the_stop_names_pass_env_and_in_place_how_to_restore_the_files(self):
        for in_place in (False, True):
            with self.subTest(in_place=in_place):
                run = self.run_for()
                run.build({})
                self.needs(run)
                with self.assertRaises(RuntimeError) as stopped:
                    run.tests(red_in_place=in_place)
                self.assertIn("--pass-env", str(stopped.exception))
                self.assertEqual("git checkout --force" in str(stopped.exception), in_place, "only an in-place checkout can leave files missing")

    def test_passing_the_variable_by_name_lets_the_same_checkout_succeed(self):
        for in_place in (False, True):
            with self.subTest(in_place=in_place):
                run = self.run_for()
                run.build({})
                self.needs(run)
                self.assertEqual(answers(run.tests(red_in_place=in_place, pass_env=[CREDENTIAL])), GREEN)


class NoOtherProgramKindStartsForTheCheckout(Fixture):
    """The kinds below are in the config before the run, and none starts: no environment reaches them."""

    def test_a_repository_config_that_names_every_other_kind_of_program_starts_none(self):
        kinds = ("diff.probe.textconv", "diff.external", "core.fsmonitor", "core.pager", "core.editor", "core.sshCommand", "core.askPass")
        run = self.run_for()
        run.build({})
        run.configure(
            {key: f'"{PY}" "{self.probe}" "{run.log}" {key} {CREDENTIAL}' for key in (*kinds, "credential.helper", "gpg.program", "hook.probe.command")}
        )
        run.configure({"hook.probe.event": "post-checkout"})
        hook = run.root / ".git" / "hooks" / "post-checkout"
        hook.write_text(f'#!/bin/sh\n"{PY}" "{self.probe}" "{run.log}" hook {CREDENTIAL}\n', encoding="utf-8")
        hook.chmod(0o755)
        for in_place in (False, True):
            with self.subTest(in_place=in_place):
                self.assertEqual(answers(run.tests(red_in_place=in_place)), GREEN)
                self.assertEqual(run.started(), [])


class ASubmodulesFilterRunsWithTheTestCommandsEnvironment(Fixture):
    def test_the_submodule_the_in_place_checkout_updates_runs_its_filter_without_the_credential(self):
        """With `submodule.recurse` set, the checkout also checks out the submodule, whose own config names a filter."""
        sub = self.tmp / "sub"
        sub.mkdir()
        git(sub, "init", "-q", "-b", "main")
        git(sub, "config", "user.email", "a@example.com")
        git(sub, "config", "user.name", "A")
        for text in ("data\n", "data2\n"):
            (sub / "s.dat").write_text(text, encoding="utf-8")
            (sub / ".gitattributes").write_text("*.dat filter=probe\n", encoding="utf-8")
            git(sub, "add", "-A")
            git(sub, "commit", "-qm", "s")
        run = self.run_for()
        run.build({}, submodule=sub)
        run.configure(run.filters("smudge"), "subm")
        run.configure({"submodule.recurse": "true"})
        self.assertEqual(answers(run.tests(red_in_place=True))[-1], ("greet", "red", "failed"))
        self.assertEqual(run.kinds(), ["smudge"], "the control: the submodule's filter ran")
        self.assertEqual(run.credentials_seen(), [], "the submodule's filter saw the credential")


class TheDelegateChecksCheckoutOfTheHeadRunsWithTheTestCommandsEnvironment(Fixture):
    def test_a_filter_in_the_config_sees_no_credential_when_the_check_checks_out_the_head(self):
        run = self.run_for()
        run.build({})
        run.configure(run.filters("smudge"))
        head, base = git(run.root, "rev-parse", "HEAD"), git(run.root, "rev-parse", "main")
        with mock.patch.dict(os.environ, {CREDENTIAL: self.value}):
            evidence, why = local_run.run_on_head(str(run.root), head, base)
        self.assertIsNotNone(evidence, why)
        self.assertEqual(run.kinds(), ["smudge"], "the control: the filter ran in the check's worktree")
        self.assertEqual(run.credentials_seen(), [], "the filter saw the credential")


if __name__ == "__main__":
    unittest.main()
