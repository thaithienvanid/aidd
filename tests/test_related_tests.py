"""A test command's `related_tests`: how `aidd test --changed` runs only the tests the runner relates to the change.

The invariants, each held by a table below:

- Only a quick check narrows. A full `aidd test`, `--require-green` (CI, the delegate's own run), and every red run run each
  command in full, so they give the same results and the same exit as with no `related_tests` anywhere in the config.
- A narrowed result says so: it carries `related_tests`, its `command` is the one that ran, the evidence is `partial`, and
  evidence that says it is a full run yet holds one exits 1, so nothing that asks for the full proof takes it.
- The runner must see every change. A changed path the command covers that matches no glob of `sees` (a lock file, a config,
  a fixture), is deleted, a link, outside the command's folder, or reads as an option runs the full command, and a note says why.
- The base decides: a head that adds or changes `related_tests` changes its command, so the base's copy also runs, in full.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  # the hermetic environment
from helpers import git

from aidd import config
from aidd.config import test_runners
from aidd.testing import related_tests, runner, verdict

PY = sys.executable.replace("\\", "/")
# The project's own runner: the full run fails while BROKEN is in the tree; its related-tests form sees nothing wrong, as a narrowed
# run that misses the failing test would. So a run that narrows passes where the full command fails.
CHECK = "import pathlib, sys\nsys.exit(0 if sys.argv[1:2] == ['--related'] or not pathlib.Path('BROKEN').exists() else 1)\n"
RELATED = '    related_tests: {{command: ["{py}", check.py, --related, "{{changed_paths}}"], sees: ["src/**"]}}\n'


def config_text(related: bool) -> str:
    return f'aidd_version: "1.0.0"\nprofile: solo\ntests:\n  - name: unit\n    command: ["{PY}", check.py]\n' + (RELATED.format(py=PY) if related else "")


def case(when_changed=None, runs_in=None, sees=("src/**",), command=("jest", "{changed_paths}")) -> dict:
    c: dict = {"name": "unit", "command": ["jest"], "related_tests": {"command": list(command), "sees": list(sees)}}
    if when_changed:
        c["when_changed"] = when_changed
    if runs_in:
        c["runs_in"] = runs_in
    return c


class WhenItNarrows(unittest.TestCase):
    """`related_tests_command` over the input space: what narrows, and each reason it runs the full command."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.top = Path(self.tmp.name)
        for rel in ("src/a.ts", "src/b.ts", "packages/api/src/x.ts", "packages/web/src/y.ts", "package-lock.json", "-x.ts", "packages/api/-y.ts", "SRC/c.ts"):
            (self.top / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.top / rel).write_text("x\n", encoding="utf-8")
        os.symlink(self.top / "src/a.ts", self.top / "src/link.ts")

    def tearDown(self):
        self.tmp.cleanup()

    def test_each_row(self):
        rows = [
            # (command, changed paths, the command it runs or None, a word of why it does not narrow)
            ("one path in sees", case(), ["src/a.ts"], ["jest", "src/a.ts"], ""),
            ("many paths in sees", case(), ["src/a.ts", "src/b.ts"], ["jest", "src/a.ts", "src/b.ts"], ""),
            ("no path", case(), [], None, "no changed path"),
            ("a lock file", case(), ["src/a.ts", "package-lock.json"], None, "package-lock.json matches no glob"),
            ("only a lock file", case(), ["package-lock.json"], None, "package-lock.json matches no glob"),
            ("a deleted file", case(), ["src/gone.ts"], None, "src/gone.ts is deleted"),
            ("a link", case(), ["src/link.ts"], None, "src/link.ts is deleted, a link"),
            ("another case of the letters", case(), ["SRC/c.ts"], None, "SRC/c.ts matches no glob"),
            ("a path read as an option", case(sees=["**"]), ["-x.ts"], None, "starts with `-`"),
            ("a path read as an option from its folder", case(runs_in="packages/api", sees=["**"]), ["packages/api/-y.ts"], None, "starts with `-`"),
            ("the base commit", case(command=("jest", "--changedSince={base_commit}")), ["src/a.ts"], ["jest", "--changedSince=abc123"], ""),
            (
                "a monorepo package, from its folder",
                case(when_changed=["packages/api/**"], runs_in="packages/api", sees=["packages/api/src/**"]),
                ["packages/api/src/x.ts", "packages/web/src/y.ts"],
                ["jest", "src/x.ts"],
                "",
            ),
            (
                "a path outside the package's folder that it covers",
                case(runs_in="packages/api", sees=["packages/**"]),
                ["packages/api/src/x.ts", "packages/web/src/y.ts"],
                None,
                "packages/web/src/y.ts lies outside packages/api",
            ),
            ("no related_tests", {"name": "unit", "command": ["jest"]}, ["src/a.ts"], None, ""),
        ]
        for label, command, paths, want, why in rows:
            with self.subTest(label):
                argv, said = related_tests.related_tests_command(command, paths, "abc123", str(self.top))
                self.assertEqual(argv, want)
                self.assertIn(why, said)
                self.assertEqual(bool(said), want is None and "related_tests" in command)

    def test_a_command_too_long_to_start_runs_in_full(self):
        many = [f"src/{'a' * 200}{i}.ts" for i in range(200)]
        for rel in many:
            (self.top / rel).write_text("x\n", encoding="utf-8")
        argv, why = related_tests.related_tests_command(case(), many, "abc", str(self.top))
        self.assertIsNone(argv)
        self.assertIn("longer than", why)


class TheFormIsCheckedAtLoad(unittest.TestCase):
    def test_each_command_that_cannot_narrow_honestly_fails_the_load(self):
        rows = [
            (["jest", "{changed_paths}"], ""),
            (["jest", "--since={base_commit}"], ""),
            (["jest", "{base_commit}", "{changed_paths}"], ""),
            (["jest", "-o"], "neither"),
            (["jest", "--files={changed_paths}"], "an argument of its own"),
            (["jest", "{changed_path}"], "no placeholder"),
            (["jest", "{}"], "no placeholder"),
        ]
        for command, why in rows:
            with self.subTest(command):
                raw = {"tests": [{"name": "u", "command": ["jest"], "related_tests": {"command": command, "sees": ["src/**"]}}]}
                problems = test_runners.related_tests_problems(raw)
                self.assertEqual(bool(problems), bool(why))
                self.assertTrue(all(why in m and p == "$.tests[0].related_tests.command" for p, m in problems))
                text = (
                    'aidd_version: "1.0.0"\nprofile: solo\ntests:\n  - name: u\n    command: [jest]\n    related_tests: '
                    + json.dumps({"command": command, "sees": ["src/**"]})
                    + "\n"
                )
                if why:
                    with self.assertRaises(config.ConfigError):
                        config.load_text(text)
                else:
                    self.assertEqual(config.load_text(text).tests[0]["related_tests"]["command"], command)

    def test_a_spec_command_has_no_related_tests(self):
        from aidd.kernel import json_schema

        command = {"name": "a", "command": ["jest"], "related_tests": {"command": ["jest", "{changed_paths}"], "sees": ["src/**"]}}
        errors = json_schema.validate({"files": [], "commands": [command]}, "common.schema.json#/$defs/tests")
        self.assertTrue(errors)


class TheSuggestion(unittest.TestCase):
    def test_a_runner_with_a_documented_mode_gets_its_form_and_any_other_none(self):
        rows = [
            (["npx", "jest", "--ci"], ["npx", "jest", "--passWithNoTests", "--findRelatedTests", "{changed_paths}"]),
            (["npx", "vitest", "run"], ["npx", "vitest", "related", "--run", "--passWithNoTests", "{changed_paths}"]),
            (["node_modules/.bin/JEST"], ["node_modules/.bin/JEST", "--passWithNoTests", "--findRelatedTests", "{changed_paths}"]),
            (["npm", "test"], None),
            (["pytest", "-q"], None),
            (["npx", "playwright", "test"], None),
            ([], None),
            ("jest", None),
        ]
        for command, want in rows:
            with self.subTest(command):
                self.assertEqual(config.related_tests_suggestion(command), want)


class OnlyAQuickCheckNarrows(unittest.TestCase):
    """The differential: each flag, over each config shape and each change, against the same repository with no `related_tests`."""

    def repo(self, base_related: bool, head_related: bool, change: str) -> Path:
        root = Path(self.tmp.name) / f"r{len(list(Path(self.tmp.name).iterdir()))}"
        root.mkdir()
        git(root, "init", "-q", "-b", "main")
        for k, v in (("user.email", "alice@example.com"), ("user.name", "Alice"), ("commit.gpgsign", "false")):
            git(root, "config", k, v)
        (root / ".aidd").mkdir()
        (root / ".gitignore").write_text("/.aidd/*/\n", encoding="utf-8")
        (root / ".aidd/config.yaml").write_text(config_text(base_related), encoding="utf-8")
        (root / "check.py").write_text(CHECK, encoding="utf-8")
        (root / "BROKEN").write_text("the full suite fails\n", encoding="utf-8")
        (root / "src").mkdir()
        (root / "src/app.ts").write_text("one\n", encoding="utf-8")
        (root / "src/old.ts").write_text("old\n", encoding="utf-8")
        (root / "package-lock.json").write_text("{}\n", encoding="utf-8")
        git(root, "add", ".")
        git(root, "commit", "-qm", "base")
        git(root, "checkout", "-qb", "feature")
        (root / ".aidd/config.yaml").write_text(config_text(head_related), encoding="utf-8")
        if change == "source":
            (root / "src/app.ts").write_text("two\n", encoding="utf-8")
        elif change == "lock file":
            (root / "package-lock.json").write_text('{"a": 1}\n', encoding="utf-8")
        else:
            (root / "src/old.ts").unlink()
        git(root, "add", "-A")
        git(root, "commit", "-qm", "change")
        return root

    def run_tests(self, root: Path, flags: dict) -> tuple[dict, list[str]]:
        return runner.run_tests(repo=str(root), base="main", out_dir=str(root / ".aidd" / "evidence"), **flags)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_run_that_asks_for_the_full_proof_narrows_and_each_verdict_is_the_one_without_related_tests(self):
        flags = {"full": {}, "require green": {"require_green": True}}  # `--changed` with `--require-green` is refused before anything runs
        quick = {"changed": True}
        for change in ("source", "lock file", "deleted"):
            # The same repository with no `related_tests`: every flag runs the one full command there, which fails on this head.
            plain, _ = self.run_tests(self.repo(False, False, change), {})
            self.assertEqual(({tuple(r["command"]) for r in plain["results"]}, verdict.exit_code(plain)), ({(PY, "check.py")}, 1))
            for shape in ((False, True), (True, True)):
                root = self.repo(*shape, change)
                for label, flag in [*flags.items(), ("changed", quick)]:
                    with self.subTest(shape=shape, change=change, flags=label):
                        ev, notes = self.run_tests(root, flag)
                        related = [r for r in ev["results"] if r.get("related_tests")]
                        full_commands = {tuple(r["command"]) for r in plain["results"]}
                        if flag is quick and change == "source" and shape[0]:
                            # Only here does the runner see every change. A head that adds the form changes the config, which no runner traces.
                            self.assertEqual([r["name"] for r in ev["results"]], ["unit"])
                            self.assertEqual(related[0]["command"], [PY, "check.py", "--related", "src/app.ts"])
                            self.assertIs(ev["partial"], True)
                            continue
                        self.assertEqual(related, [], notes)
                        self.assertEqual({tuple(r["command"]) for r in ev["results"]}, full_commands)
                        self.assertEqual(verdict.exit_code(ev), verdict.exit_code(plain))
                        self.assertEqual(verdict.exit_code(ev), 1, "the full command fails on this head")
                        if flag is quick:
                            self.assertTrue(any(n.startswith("unit ran in full") for n in notes), notes)

    def test_evidence_that_says_it_is_full_and_holds_a_narrowed_result_exits_1(self):
        narrowed = {"name": "unit", "command": ["jest", "a.ts"], "red_green": "green", "status": "passed", "exit": 0, "related_tests": True}
        plain = {**narrowed, "related_tests": None}
        rows = [({"results": [narrowed]}, 1), ({"results": [narrowed], "partial": True}, 0), ({"results": [plain]}, 0)]
        for evidence, code in rows:
            with self.subTest(evidence):
                self.assertEqual(verdict.exit_code(evidence), code)


if __name__ == "__main__":
    unittest.main()
