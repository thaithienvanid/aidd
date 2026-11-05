"""A mistyped command, flag, value, word, or config key is told which one was wrong, what the valid ones are, and the next
step that works, and exits 2. The tables read the parser itself, so a new flag with `choices=` or a spread of values is
covered without a new test."""

import argparse
import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import make_repo

from aidd import config
from aidd.cli import app, arguments, grammar
from aidd.cli import parser as cli_parser
from aidd.kernel import text


def run(*argv: str, cwd: Path | None = None) -> tuple[int, str]:
    """`aidd <argv>` in this process: its exit code and what it wrote to stderr."""
    here = os.getcwd()
    err = io.StringIO()
    os.chdir(cwd or here)
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            try:
                code = app.main(list(argv))
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 2
    finally:
        os.chdir(here)
    return code, err.getvalue()


def commands() -> dict[str, argparse.ArgumentParser]:
    top = cli_parser.build_parser()
    sub = next(a for a in top._actions if isinstance(a, argparse._SubParsersAction))
    return dict(sub.choices)


def options_of(command: argparse.ArgumentParser) -> list[argparse.Action]:
    return [a for a in command._actions if a.option_strings and not isinstance(a, argparse._HelpAction)]


def wrong(choices) -> str:
    """A value that is no choice but reads like one: the first choice mistyped (an int choice: a number past them all)."""
    first = list(choices)[0]
    return str(max(choices) + 1) if isinstance(first, int) else f"{first}q"


class ChoiceTableTests(unittest.TestCase):
    """Every flag or word with fixed choices, found in the parser: a wrong value is an error that names the flag, offers
    the closest choice or lists them, and exits 2."""

    def cases(self):
        for name, command in commands().items():
            for action in command._actions:
                if action.choices and not isinstance(action, argparse._SubParsersAction):
                    yield name, action

    def test_a_wrong_value_for_any_choice_names_its_flag_and_the_choices(self):
        seen = 0
        for name, action in self.cases():
            flag = action.option_strings[0] if action.option_strings else None
            bad = wrong(action.choices)
            argv = [name, *([flag] if flag else []), bad]
            with self.subTest(argv=argv):
                code, err = run(*argv)
                first = err.splitlines()[0]
                self.assertEqual(code, 2)
                self.assertTrue(first.startswith(f"aidd {name} {flag}: " if flag else f"aidd {name}: "), first)
                self.assertIn(f"'{bad}' is not a choice.", first)
                self.assertTrue("Did you mean `" in first or all(str(c) in first for c in action.choices), first)
                if "Did you mean `" in first:
                    self.assertIn(first.split("Did you mean `")[1].split("`")[0], [str(c) for c in action.choices], "the guess is a valid value")
                self.assertIn(f"`aidd {name} --help` shows every option.", err)
                seen += 1
        self.assertGreater(seen, 10)  # the table found the flags, never an empty loop

    def test_a_far_value_for_any_choice_lists_the_choices(self):
        seen = 0
        for name, action in self.cases():
            flag = action.option_strings[0] if action.option_strings else None
            bad = "99" if isinstance(list(action.choices)[0], int) else "zzzzzzzz"
            argv = [name, *([flag] if flag else []), bad]
            with self.subTest(argv=argv):
                code, err = run(*argv)
                first = err.splitlines()[0]
                self.assertEqual(code, 2)
                self.assertNotIn("Did you mean", first)
                self.assertIn(f"The choices: {', '.join(str(c) for c in action.choices)}.", first)
                seen += 1
        self.assertGreater(seen, 10)

    def test_a_close_value_is_offered_by_name(self):
        for argv, guess in (
            (("init", "--ci", "gitub"), "github"),
            (("init", "--profile", "tem"), "team"),
            (("risk", "--paths", "a.py", "--change-type", "fet"), "feat"),
            (("new", "specc"), "spec"),
        ):
            with self.subTest(argv=argv):
                code, err = run(*argv)
                self.assertEqual(code, 2)
                self.assertIn(f"Did you mean `{guess}`?", err.splitlines()[0])
        self.assertEqual(run("init", "--ci", "gitub")[1].splitlines()[0], "aidd init --ci: 'gitub' is not a choice. Did you mean `github`?")

    def test_a_flag_that_spreads_over_values_is_named_here_with_why_it_can_stay(self):
        """A `nargs="+"` flag swallows the positional that follows it, so each one needs a reason; a new one fails here."""
        stays = {
            ("risk", "--paths"): "risk takes no positional, so nothing follows to be swallowed",
            ("new", "--paths"): "a Spec's scope is a list of paths, as `risk --paths` takes; new names the word it took (test below)",
        }
        found = {(name, a.option_strings[0]) for name, command in commands().items() for a in options_of(command) if a.nargs in ("+", "*")}
        self.assertEqual(found, set(stays), "a flag that takes a spread of values must be repeatable instead, or named with its reason")


class UnknownNameTests(unittest.TestCase):
    def test_an_unknown_explain_word_names_the_closest_and_exits_2(self):
        code, err = run("explain", "pr.mrge")
        self.assertEqual(code, 2)
        self.assertTrue(
            err.startswith("aidd explain: 'pr.mrge' is not a word aidd knows. Did you mean `pr.merge`? `aidd explain --list` lists every word"), err
        )
        code, err = run("explain", "flibbertigibbet")
        self.assertEqual(code, 2)
        self.assertNotIn("Did you mean", err)
        self.assertIn("`aidd explain --list` lists every word", err)

    def test_the_list_flag_of_a_command_that_has_a_list_word_says_the_word(self):
        for command in ("standard", "records"):
            with self.subTest(command=command):
                code, err = run(command, "--list")
                self.assertEqual(code, 2)
                self.assertIn(f"aidd {command}: unknown option --list. Did you mean `aidd {command} list`?", err)

    def test_every_command_with_a_word_to_list_does_the_same(self):
        """An optional word with choices (`standard list|add`) gets its flag spelling answered, found in the parser."""
        for name, command in commands().items():
            for action in command._actions:
                for word in (action.choices or ()) if action.nargs == "?" and not action.option_strings else ():
                    if f"--{word}" in [o for a in command._actions for o in a.option_strings]:
                        continue  # the flag exists: it is no mistake
                    with self.subTest(command=name, word=word):
                        code, err = run(name, f"--{word}")
                        self.assertEqual(code, 2)
                        self.assertIn(f"Did you mean `aidd {name} {word}`?", err)

    def test_an_unknown_config_key_names_the_closest_key(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d), "solo")
            path = root / config.CONFIG_PATH
            path.write_text(path.read_text(encoding="utf-8").replace("\nowners:", "\nownres:", 1), encoding="utf-8")
            code, err = run("status", cwd=root)
            self.assertEqual(code, 1)
            self.assertRegex(err, r"line \d+: \$: unknown field 'ownres'\. Did you mean `owners`\?")
            path.write_text(path.read_text(encoding="utf-8").replace("\nownres:", "\nzzzzzz:", 1), encoding="utf-8")
            code, err = run("status", cwd=root)
            self.assertIn("unknown field 'zzzzzz'", err)
            self.assertNotIn("Did you mean", err)

    def test_the_closest_word_is_a_typo_never_a_guess(self):
        self.assertEqual(text.closest("gitub", ["github", "gitlab", "none"]), "github")
        self.assertIsNone(text.closest("next", ["context"], cutoff=0.75))
        self.assertEqual(text.did_you_mean("gitub", ["github"], form="--ci {}"), "Did you mean `--ci github`?")
        self.assertEqual(text.did_you_mean("zzz", ["github"]), "")


class GrammarTests(unittest.TestCase):
    def test_the_parser_still_builds_every_command(self):
        self.assertEqual(set(commands()), set(grammar.ADD_COMMAND) | {"help"})


class InitFlagTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def init(self, *flags: str) -> tuple[int, str]:
        return run("init", str(self.root), "--dry-run", "--profile", "solo", "--test", "true", *flags)

    def test_approvers_take_one_value_each_so_a_word_after_them_is_the_path(self):
        self.assertEqual(cli_parser.build_parser().parse_args(["init", "--approvers", "@me", "--approvers", "@you", "sub"]).approvers, ["@me", "@you"])
        args = cli_parser.build_parser().parse_args(["init", "--approvers", "@me", "sub"])
        self.assertEqual((args.approvers, args.path), (["@me"], "sub"))
        code, err = self.init("--approvers", "@me,@you", "--approvers", "@them")
        self.assertEqual((code, err), (0, ""))

    def test_harness_none_beside_a_name_is_an_error_that_names_both(self):
        code, err = self.init("--harness", "none", "--harness", "codex")
        self.assertEqual(code, 2)
        self.assertIn("--harness none says no coding agent, so give it alone: it cannot stand beside --harness codex", err)
        self.assertEqual(self.init("--harness", "none", "--harness", "none"), (0, ""))

    def test_security_ci_under_no_ci_gives_one_note(self):
        code, err = self.init("--ci", "none", "--security-ci")
        self.assertEqual((code, err.count("note: ")), (0, 1))
        self.assertIn("you gave --ci none, so --security-ci writes nothing", err)
        code, err = self.init("--security-ci")  # no --ci, and this repository has no remote
        self.assertIn("this repository has no git remote, so init writes no CI files, so --security-ci writes nothing", err)
        self.assertNotIn("--ci none,", err)
        self.assertEqual(self.init("--ci", "github", "--security-ci"), (0, ""))
        self.assertEqual(self.init("--ci", "none"), (0, ""))

    def test_the_init_help_says_what_each_flag_does_and_what_leaving_it_out_means(self):
        init = commands()["init"]
        helps = {a.option_strings[0]: a.help for a in options_of(init)}
        for flag in ("--force", "--test", "--approvers", "--ref", "--security-ci"):
            self.assertTrue(helps[flag], flag)
        for flag in ("--test", "--approvers", "--ref"):
            self.assertIn("(default: ", helps[flag], f"{flag} says what leaving it out means")
        self.assertIn("keep every value in the config", helps["--force"])
        self.assertNotIn("overwrite existing files", helps["--force"])
        self.assertIn("`--ci none` writes no CI", helps["--security-ci"])


class NewPathsTests(unittest.TestCase):
    def test_a_title_after_paths_is_named_as_the_word_paths_took(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d), "solo")
            code, err = run("new", "spec", "--paths", "app.py", "Add a discount", cwd=root)
        self.assertEqual(code, 2)
        self.assertIn("--paths took 'app.py', 'Add a discount': put the title first", err)


class RecordsTypeTests(unittest.TestCase):
    def test_records_type_takes_the_types_records_json_owns(self):
        from aidd.kernel import resources

        action = next(a for a in options_of(commands()["records"]) if a.option_strings == ["--type"])
        self.assertEqual(list(action.choices), list(resources.load_json("records.json")["types"]))
        code, err = run("records", "--type", "deciion")
        self.assertEqual(code, 2)
        self.assertIn("aidd records --type: 'deciion' is not a choice. Did you mean `decision`?", err)


class RiskQualifierTests(unittest.TestCase):
    """One table maps each `risk` qualifier to its modes. Every qualifier beside a mode it does not go with, and every pair
    of modes, is an error that names them, found in the table and the parser."""

    GIVEN = {"change_type": ["--change-type", "fix"], "dimension": ["--dimension", "data"], "irreversible": ["--irreversible"], "area": ["--area", "payments"], "branch": ["--branch", "own"],
             "folder": ["--folder", "."], "role": ["--role", "developer"], "route": ["--route", "major"]}  # fmt: skip
    MODE = {"paths": ["--paths", "a.py"], "command_line": ["--command", "ls"], "action": ["--action", "pr.merge"], "list": ["--list"], "suggest": ["--suggest"]}

    def test_the_table_names_every_qualifier_flag_the_parser_has(self):
        from aidd.cli.commands import work

        flags = {a.option_strings[0] for a in options_of(commands()["risk"])}
        modes = set(work.RISK_MODES.values())
        self.assertEqual(flags - modes - {"--json", "--suggest"}, {q[0] for q in work.RISK_QUALIFIERS.values()})

    def test_a_qualifier_beside_a_mode_it_does_not_go_with_is_an_error(self):
        from aidd.cli.commands import work

        checked = 0
        for attr, (flag, goes_with, _meaning, _otherwise) in work.RISK_QUALIFIERS.items():
            for mode, argv in self.MODE.items():
                if work.RISK_MODES[mode] in goes_with:
                    continue
                with self.subTest(qualifier=flag, mode=work.RISK_MODES[mode]):
                    code, err = run("risk", *argv, *self.GIVEN[attr])
                    self.assertEqual(code, 2)
                    self.assertIn(f"{flag} ", err.splitlines()[0])
                    self.assertIn(f"you gave {work.RISK_MODES[mode]}", err)
                    checked += 1
        self.assertGreater(checked, 20)

    def test_two_modes_say_give_only_one_of_and_name_both(self):
        code, err = run("risk", "--paths", "a.py", "--command", "ls")
        self.assertEqual(code, 2)
        self.assertIn("give only one of --paths, --command, --action, --list, or --suggest; you gave --paths and --command", err)
        self.assertIn("give one of --paths, --command, --action, --list, or --suggest (", run("risk")[1])

    def test_a_qualifier_with_its_mode_still_answers(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d), "solo")
            self.assertEqual(run("risk", "--command", "ls", "--branch", "own", cwd=root)[0], 0)
            self.assertEqual(run("risk", "--paths", "a.py", "--change-type", "fix", "--dimension", "cost", "--irreversible", cwd=root)[0], 0)
            self.assertEqual(run("risk", "--action", "pr.merge", "--area", "payments", "--role", "developer", cwd=root)[0], 0)


class NamedCommandTests(unittest.TestCase):
    def test_every_type_the_skill_and_the_docs_pass_to_new_is_a_type(self):
        """A command the skill hands an agent must work as written: `aidd new service` was no type."""
        import re

        from helpers import ROOT

        types = set(grammar.new_types())
        seen = 0
        for folder in (".agents/skills/aidd", "docs", "plugins"):
            for path in (ROOT / folder).rglob("*.md"):
                for word in re.findall(r"`aidd new ([a-z][a-z-]*)[ `]", path.read_text(encoding="utf-8")):
                    with self.subTest(file=str(path.relative_to(ROOT)), word=word):
                        self.assertIn(word, types)
                    seen += 1
        self.assertGreater(seen, 20)


class StandardTests(unittest.TestCase):
    def test_stack_or_ids_without_add_are_an_error_that_names_add(self):
        for argv, named in (
            (("--stack", "python-cli"), "aidd standard add --stack python-cli"),
            (("list", "python/ruff-lint-format"), "aidd standard add python/ruff-lint-format"),
        ):
            with self.subTest(argv=argv):
                code, err = run("standard", *argv)
                self.assertEqual(code, 2)
                self.assertIn(f"so it goes with add: run `{named}`", err)


class ExplainHelpTests(unittest.TestCase):
    def test_the_explain_lines_of_the_help_name_every_kind_explain_knows(self):
        from aidd import knowledge

        blob = {
            name: " ".join(body.split())
            for name, body in (("aidd help --all", help_text("help", "--all")), ("aidd help explain", help_text("help", "explain")))
        }
        for where, shown in blob.items():
            for kind in knowledge.EXPLAIN_TYPES:
                kind = kind.replace("_", " ")
                with self.subTest(where=where, kind=kind):
                    self.assertRegex(shown, rf"\b(?:a|an) {kind}\b")


def help_text(*argv: str) -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        try:
            app.main(list(argv))
        except SystemExit:
            pass
    return out.getvalue()


class StrayWordTests(unittest.TestCase):
    def test_a_word_no_argument_takes_is_unexpected_and_named(self):
        code, err = run("init", "--dry-run", "one", "two")
        self.assertEqual(code, 2)
        self.assertEqual(err.splitlines()[0], "aidd init: unexpected 'two'.")

    def test_a_person_after_approvers_or_specialist_says_how_to_give_more(self):
        for flags, flag in ((("--approvers", "@a"), "--approvers"), (("--specialist", "security=@a"), "--specialist")):
            for stray in ("@b", "email:b@example.com"):
                with self.subTest(flag=flag, stray=stray):
                    code, err = run("init", "--dry-run", *flags, "tidy", stray)
                    self.assertEqual(code, 2)
                    self.assertIn(f"unexpected '{stray}'. Repeat {flag} for each", err)
        with tempfile.TemporaryDirectory() as d:  # the person read as the path
            code, err = run("init", "--approvers", "@a", "@b", cwd=Path(d))
        self.assertEqual(code, 2)
        self.assertIn("@b is not a directory. Repeat --approvers for each person, or join them with commas.", err)
        self.assertNotIn("Repeat", run("init", "--dry-run", "tidy", "@b")[1])  # no flag came before it

    def test_a_value_with_spaces_is_not_a_person_and_the_help_does_not_say_it_is(self):
        approvers = next(a for a in options_of(commands()["init"]) if a.option_strings == ["--approvers"])
        self.assertNotIn("space", approvers.help)
        self.assertIn("join people with commas", approvers.help)
        code, err = run("init", "--dry-run", "--approvers", "@a @b")
        self.assertEqual(code, 2)
        self.assertIn("is not a person", err)


class SpecialistPoolTests(unittest.TestCase):
    def test_a_pool_no_dimension_asks_is_an_error_with_the_closest(self):
        code, err = run("init", "--dry-run", "--specialist", "secrity=@a")
        self.assertEqual(code, 2)
        self.assertIn("--specialist 'secrity' is not a pool aidd asks. Did you mean `security`?", err)
        code, err = run("init", "--dry-run", "--specialist", "design=@a")
        self.assertIn("The pools: compliance, data, finance, privacy, security.", err)

    def test_every_pool_a_dimension_names_is_accepted(self):
        for pool in config.POOL_OF.values():
            self.assertEqual(arguments.specialists([f"{pool}=@a"]), {pool: ["@a"]})


class CaseTests(unittest.TestCase):
    def test_a_word_in_the_wrong_case_finds_its_command(self):
        self.assertIn("Did you mean `aidd status`?", run("STATUS")[1])
        self.assertEqual(text.closest("GitHub", ["github", "gitlab"]), "github")


class McpRiskTests(unittest.TestCase):
    def test_a_qualifier_beside_the_wrong_mode_is_the_same_error_the_cli_gives(self):
        from aidd.cli import mcp_server

        here = os.getcwd()
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d), "solo")
            os.chdir(root)  # the tool runs at the repository's top
            try:
                bad, said = mcp_server.call("risk", {"paths": ["a.py"], "branch": "own"}, str(root))
                self.assertTrue(bad)
                self.assertIn("--branch is the branch a command or an action reaches, so it goes with --command or --action only, and you gave --paths", said)
                bad, said = mcp_server.call("risk", {"command": "ls", "change_type": "fix"}, str(root))
                self.assertTrue(bad)
                self.assertIn("--change-type", said)
                ok, _ = mcp_server.call("risk", {"command": "ls", "branch": "own"}, str(root))
                self.assertFalse(ok)
            finally:
                os.chdir(here)

    def test_irreversible_goes_to_the_cli_with_paths_and_is_refused_beside_any_other_mode(self):
        from aidd.cli import mcp_server

        here = os.getcwd()
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d), "solo")
            os.chdir(root)
            try:
                bad, said = mcp_server.call("risk", {"paths": ["a.py"]}, str(root))
                self.assertFalse(bad)
                self.assertEqual(json.loads(said)["route"], "minor")
                bad, said = mcp_server.call("risk", {"paths": ["a.py"], "irreversible": True}, str(root))
                self.assertFalse(bad)
                self.assertEqual(json.loads(said)["route"], "major")
                bad, said = mcp_server.call("risk", {"command": "ls", "irreversible": True}, str(root))
                self.assertTrue(bad)
                self.assertIn("--irreversible", said)
                bad, said = mcp_server.call("risk", {"paths": ["a.py"], "irreversible": "yes"}, str(root))
                self.assertTrue(bad)
                self.assertIn("irreversible must be true or false", said)
            finally:
                os.chdir(here)


class ValueShapeTests(unittest.TestCase):
    """Two flags that read alike say the shape of what they take: a folder, a file, an id, or an id or a path."""

    def test_the_value_names_say_a_folder_a_file_and_an_id_or_a_path(self):
        shown = {
            (command, flag): next(a.metavar for a in options_of(parser) if flag in a.option_strings)
            for command, flag in (("test", "--out"), ("explore", "--out"), ("test", "--spec"), ("delegate", "--spec"))
            for parser in [commands()[command]]
        }
        self.assertEqual(shown, {("test", "--out"): "DIR", ("explore", "--out"): "PATH", ("test", "--spec"): "ID_OR_PATH", ("delegate", "--spec"): "ID"})


class TypedDefaultTests(unittest.TestCase):
    def test_change_type_typed_as_its_default_beside_another_mode_is_still_an_error(self):
        code, err = run("risk", "--command", "ls", "--change-type", "feat")
        self.assertEqual(code, 2)
        self.assertIn("--change-type is the change type of planned paths", err)

    def test_the_default_shows_in_the_generated_docs(self):
        from helpers import ROOT

        row = next(line for line in (ROOT / "docs" / "CLI.md").read_text(encoding="utf-8").splitlines() if line.startswith("| `risk` |"))
        self.assertIn("(default `feat`)", row)
