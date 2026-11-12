"""The contract aidd's own CLI keeps with a person or a script that calls it. Each table is read from the parser, so a new
command, flag, or choice is held to it with no new test code:

- a command's `--json` follows the schema its help names, and a schema its help names exists;
- every command's `--help` exits 0, and an option with a default says what that default is;
- `init --dry-run` with any choice of any choice flag writes nothing and names every file the real run writes;
- `init --force` with any flag changes in the config only the values that flag sets.

A wrong value for a choice flag exits 2 and names the flag and the valid values: `test_cli_mistakes.py` holds that table."""

import argparse
import contextlib
import io
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import aidd_here, git, make_repo
from init_plan_helpers import files_of, repo

from aidd.cli import app
from aidd.cli import parser as cli_parser
from aidd.kernel import documents, json_schema, resources
from aidd.setup import config_keep


def commands() -> dict[str, argparse.ArgumentParser]:
    top = cli_parser.build_parser()
    sub = next(a for a in top._actions if isinstance(a, argparse._SubParsersAction))
    return dict(sub.choices)


def options_of(command: argparse.ArgumentParser) -> list[argparse.Action]:
    return [a for a in command._actions if a.option_strings and not isinstance(a, argparse._HelpAction)]


def named_schemas() -> dict[str, list[str]]:
    """Each command with a `--json`, and the schemas that flag's help names (`records.schema.json#/$defs/list` when it names a definition)."""
    found = {}
    for name, command in commands().items():
        for action in options_of(command):
            if "--json" in action.option_strings:
                found[name] = [
                    f"{m[0]}#/$defs/{m[1]}" if m[1] else m[0] for m in re.findall(r"schemas/([\w-]+\.schema\.json)(?:, \$defs/(\w+))?", action.help or "")
                ]
    return found


class JsonOutputTests(unittest.TestCase):
    # How to call each command so it prints JSON in a repository: the arguments, then the schema the output must follow.
    CALLS = (
        (("doctor",), "doctor.schema.json"),
        (("standard",), "standard-list.schema.json"),
        (("standard", "--stacks"), "stack-list.schema.json"),
        (("status",), "status.schema.json"),
        (("risk", "--paths", "app.py"), "risk.schema.json"),
        (("records",), "records.schema.json#/$defs/list"),
        (("recall", "spec"), "recall.schema.json"),
        (("validate",), "validate.schema.json"),
        (("explain", "pr.merge"), "explain.schema.json"),
    )
    # A schema its command names but this repository cannot print, with why: a test of that command holds it.
    ELSEWHERE = {
        "records.schema.json#/$defs/added": "`records add` writes a record, so tests/test_records.py holds it",
        "delegate-check.schema.json": "`delegate check` needs a delegation and a platform, so tests/test_delegation_check.py holds it",
        "knowledge.schema.json": "`eval standards --online` fetches each citation URL, and aidd tests use no network",
    }

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = make_repo(Path(cls.tmp.name) / "repo", "team")
        (cls.root / "app.py").write_text("print(1)\n", encoding="utf-8")

    def test_every_schema_a_help_names_is_a_schema_file(self):
        named = named_schemas()
        self.assertGreater(len(named), 8)  # the table found the commands, never an empty loop
        for command, schemas in named.items():
            for schema in schemas:
                with self.subTest(command=command, schema=schema):
                    file, _, fragment = schema.partition("#")
                    node = resources.load_json(file)
                    for part in fragment.split("/")[1:]:
                        self.assertIn(part, node, f"{file} has no {fragment}")
                        node = node[part]

    def test_every_schema_a_help_names_is_checked_here_or_named_with_why_not(self):
        wanted = {s for schemas in named_schemas().values() for s in schemas}
        self.assertEqual(wanted - {s for _, s in self.CALLS}, set(self.ELSEWHERE), "a new --json schema needs a call in CALLS, or a reason in ELSEWHERE")

    def test_each_json_output_follows_the_schema_its_help_names(self):
        named = named_schemas()
        for argv, schema in self.CALLS:
            with self.subTest(argv=argv):
                self.assertIn(schema, named[argv[0]], "the call checks a schema its command's help names")
                done = aidd_here(*argv, "--json", cwd=self.root)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertEqual(json_schema.validate(json.loads(done.stdout), schema), [])


class HelpTests(unittest.TestCase):
    def test_every_command_has_a_help_that_exits_0_and_shows_its_usage(self):
        for name in commands():
            with self.subTest(command=name):
                out = io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                    code = None
                    try:
                        app.main([name, "--help"])
                    except SystemExit as stop:
                        code = stop.code
                self.assertEqual(code, 0)
                self.assertIn(f"usage: aidd {name}", out.getvalue())

    def test_every_option_with_a_default_says_what_the_default_is_in_the_help(self):
        seen = 0
        for name, command in commands().items():
            formatter = command._get_formatter()
            for action in command._actions:
                if isinstance(action, (argparse._HelpAction, argparse._SubParsersAction)) or action.nargs == 0:
                    continue
                if action.default in (None, "", False, argparse.SUPPRESS):
                    continue
                with self.subTest(command=name, option=action.option_strings or action.dest):
                    shown = formatter._expand_help(action)
                    self.assertIn("(default: ", shown)
                    seen += 1
        self.assertGreater(seen, 10)


# A value for each flag of `init` that takes one and has no fixed choices.
OPEN_VALUES = {
    "--ref": "v1.0.0",
    "--approvers": "@c",
    "--specialist": "security=@s",
    "--test": "make check",
    "--environment": "production=main",
    "--own-environment": "dev=dev",
    "--link": ".cursor/skills",
}
# What leaving out a flag of `init` that takes no value means, for a run with all its other flags: the ones that do not change the plan.
NOT_RUN_FLAGS = {"--help", "--dry-run", "--force"}


def flag_runs() -> list[list[str]]:
    """One run of `init` for each flag but `--dry-run` and `--force`, with the first choice of a flag with choices."""
    runs = []
    for action in options_of(commands()["init"]):
        flag = action.option_strings[0]
        if flag in NOT_RUN_FLAGS:
            continue
        runs.append(
            [flag] if action.nargs == 0 else [flag, str(action.choices[0]) if action.choices else OPEN_VALUES[flag]]
        )  # a new flag with a value needs one in OPEN_VALUES
    return runs


def choice_runs() -> list[list[str]]:
    """Runs of `init` that give every choice of every flag with choices, and every other flag once, in few runs: each costs a
    pass over git. A flag that takes one choice gives its first choice in the first run, its second in the second, and so on.
    A flag that repeats takes all its choices in one run (with the other flags, unless one of them is `none`, which says no choice and goes there instead)."""
    single: list[list[str]] = []  # the flags that take one choice, each with its choices
    runs: list[list[str]] = []
    rest: list[str] = []
    for action in options_of(commands()["init"]):
        flag = action.option_strings[0]
        if flag in NOT_RUN_FLAGS:
            continue
        if not action.choices:
            rest += [flag] if action.nargs == 0 else [flag, OPEN_VALUES[flag]]  # a new flag with a value needs one in OPEN_VALUES
        elif isinstance(action, argparse._AppendAction):
            every = [x for c in action.choices if c != "none" for x in (flag, str(c))]
            if "none" in action.choices:
                runs.append(every)  # `none` goes beside the other flags, and the choices that are not none have a run
                rest += [flag, "none"]
            else:
                rest += every
        else:
            single.append([flag, *map(str, action.choices)])
    most = max(len(flag_and_choices) - 1 for flag_and_choices in single)
    for i in range(most):
        runs.append([x for flag, *choices in single if i < len(choices) for x in (flag, choices[i])])
    return [*runs, rest]


# The record of the team files, which a run with `--aidd-team` writes and its dry run names.
TEAM_RECORD = ".aidd/team-files.json"


class InitFlagTests(unittest.TestCase):
    """One repository, built once; each case works in its own copy."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.template = repo(cls.tmp.name, "template")

    def copy(self, parent: str, name: str) -> Path:
        root = Path(parent).resolve() / name
        shutil.copytree(self.template, root, symlinks=True)
        return root

    def test_the_runs_cover_every_flag_and_every_choice_of_init(self):
        every = {a.option_strings[0] for a in options_of(commands()["init"])} - NOT_RUN_FLAGS
        given = {x for run in choice_runs() for x in run if x.startswith("--")}
        self.assertEqual(given, every)
        choices = {a.option_strings[0]: {str(c) for c in a.choices} for a in options_of(commands()["init"]) if a.choices}
        for flag, wanted in choices.items():
            asked = {run[i + 1] for run in choice_runs() for i, word in enumerate(run) if word == flag}
            self.assertEqual(asked, wanted, flag)
        self.assertEqual({r[0] for r in flag_runs()}, every)

    def test_a_dry_run_writes_nothing_and_names_every_file_the_real_run_writes(self):
        for flags in choice_runs():
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as d:
                dry, real = self.copy(d, "dry"), self.copy(d, "real")
                before = files_of(real)
                said = aidd_here("init", "--dry-run", *flags, cwd=dry)
                self.assertEqual((said.returncode, files_of(dry)), (0, before), said.stderr)
                done = aidd_here("init", *flags, cwd=real)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                after = files_of(real)
                for rel in sorted(rel for rel, text in after.items() if before.get(rel) != text):
                    folders = ["/".join(Path(rel).parts[:i]) for i in range(1, len(Path(rel).parts))]
                    self.assertTrue(rel in said.stdout or any(f"would vendor {folder} " in said.stdout for folder in folders), f"the dry run names {rel}")

    def test_the_dry_run_names_the_record_of_team_files_the_real_run_writes(self):
        with tempfile.TemporaryDirectory() as d:
            said = aidd_here("init", "--dry-run", "--aidd-team", cwd=self.copy(d, "dry"))
            self.assertIn(TEAM_RECORD, said.stdout)


class ForceKeepsConfigTests(unittest.TestCase):
    """`init --force` with a flag changes in the config only the values that flag sets, and with a flag that sets none, nothing."""

    EDITED = (
        'aidd_version: "1.0.0"\n'
        "profile: team\n"
        "\n"
        "owners:\n"
        '  approvers: ["@a", "@b"]\n'
        '  reviewers: ["@r"]\n'
        "\n"
        "tests:\n"
        "  - name: unit\n"
        "    command: [make, test]\n"
        "\n"
        "# my own note: keep this comment\n"
        "specs_dir: my-specs\n"
        "proposals_dir: my-proposals\n"
        "risks:\n"
        "  rules:\n"
        "    - {action: pr.open, level: allow}\n"
    )
    # The top-level config key each option in `config_keep.SETS` sets, by its flag.
    SETS_KEY = {
        "--profile": "profile",
        "--approvers": "owners",
        "--specialist": "owners",
        "--test": "tests",
        "--environment": "environments",
        "--own-environment": "environments",
        "--delegate": "delegation",
        "--compliance-target": "project",
    }

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.template = repo(cls.tmp.name, "template")
        done = aidd_here("init", "--profile", "team", "--approvers", "@a", cwd=cls.template)
        assert done.returncode == 0, done.stderr
        git(cls.template, "add", "-A")
        git(cls.template, "commit", "-qm", "day 0")

    def test_the_table_names_the_flag_of_every_value_force_can_set(self):
        flags = {flag for _, words in config_keep.SETS.values() for flag in re.findall(r"--[a-z-]+", words)}
        self.assertEqual(flags, set(self.SETS_KEY))

    def test_with_any_flag_force_changes_only_the_values_that_flag_sets(self):
        before = documents.parse_yaml(self.EDITED, "config")
        runs = flag_runs()
        sets = [run for run in runs if run[0] in self.SETS_KEY]
        others = [x for run in runs if run[0] not in self.SETS_KEY for x in run]  # the flags that set no value, in one run: each costs a pass over git
        for flags in [*sets, others]:
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as d:
                root = Path(d).resolve() / "r"
                shutil.copytree(self.template, root, symlinks=True)
                path = root / ".aidd" / "config.yaml"
                path.write_text(self.EDITED, encoding="utf-8")
                done = aidd_here("init", "--force", *flags, cwd=root)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                after = documents.parse_yaml(path.read_text(encoding="utf-8"), "config")
                moved = {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}
                self.assertLessEqual(moved, {self.SETS_KEY[flags[0]]} if flags[0] in self.SETS_KEY else set())  # the run of the others sets no value
                for stay in ("# my own note: keep this comment", "specs_dir: my-specs", "proposals_dir: my-proposals", "{action: pr.open, level: allow}"):
                    self.assertIn(stay, path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
