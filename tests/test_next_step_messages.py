"""Every stop says why and what to do next (docs/METHOD.md, "aidd must not make the team slower than working without
it"). A gate finding that fails or holds a change carries a fix; a guard denial ends with the next step, a command to
run or the person or file to turn to; and `aidd validate` names the file of each error and says what to do next.

The guard's next step is checked by its wording: a clause that starts with an action (`hand`, `ask`, `run`, `add`, ...)
or a command to run. A bare "stop" or "use" is not enough as the only action, so a reworded denial that only says no
fails here. Every `aidd <command> --flag` a fix, a denial, or a validate message names is one the parser has, and every
rulebook fix names something to act on: a command, a file or path, or a person or role to turn to."""

import argparse
import ast
import contextlib
import copy
import dataclasses
import io
import json
import os
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from helpers import ROOT, check_edit, git, make_repo

from aidd import gate
from aidd.evals import examples
from aidd.cli import app
from aidd.cli import parser as cli_parser
from aidd.gate import rulebook
from aidd.guard import command_check, denial_log, mcp_tools, pre_tool, verdicts

VERBS = (
    "add|amend|answer|apply|ask|bind|call|change|commit|copy|correct|draft|edit|exclude|fill|finish|fix|hand|install|keep|leave|let|"
    "link|list|mark|meet|move|name|open|post|push|put|queue|read|record|remove|rename|report|retry|rewrite|run|save|set|"
    "spawn|split|squash|start|stop|take|tell|try|use|wait|widen|write"
)
# A next step: a clause that starts with an action, or a command in backticks that starts with `aidd`.
# `aidd approve` and `aidd land` are a person's: a denial that names one names what it refused, not a next step.
NEXT_STEP = re.compile(
    rf"(?:^|[.;:!?]\s+|,\s+(?:or|and|then|so)\s+|\b(?:then|so|instead,?|or)\s+)(?P<verb>{VERBS})\b|(?P<command>`aidd (?!approve\b|ship\b))", re.I
)
# Actions that say no more than "do not go on": alone, they leave the reader with nothing to do.
BARE = frozenset({"stop", "use"})


def has_next_step(text: str) -> bool:
    """A clause that starts with an action other than a bare "stop" or "use", or an `aidd` command an agent may run."""
    return any(m.group("command") or m.group("verb").lower() not in BARE for m in NEXT_STEP.finditer(text))


# What a rulebook fix may point at: a command or a config key in backticks, a file or a path, or a person or role.
COMMAND_OR_KEY = re.compile(r"`[^`]+`")
FILE_OR_PATH = re.compile(r"\b[a-z0-9_.<>*-]+/[\w./<>*-]+|\b[\w-]+\.(?:md|toml|json|ya?ml|py)\b")
PERSON = re.compile(r"\b(?:person|people|human|administrator|maintainers?|owners?|author|approvers?|reviewers?|commander|member)\b", re.I)


def fix_problems(fix: str) -> list[str]:
    """Why a rulebook fix gives the reader nothing to do, or none. A person or role to turn to is a step by itself;
    otherwise the fix needs an action and something to act on."""
    if PERSON.search(fix):
        return []
    problems = [] if has_next_step(fix) else ["no action other than a bare stop or use"]
    if not (COMMAND_OR_KEY.search(fix) or FILE_OR_PATH.search(fix)):
        problems.append("names no command, file, path, person, or role")
    return problems


AIDD_COMMAND = re.compile(r"`aidd ([^`]*)`")


def _subcommands(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    return next((dict(a.choices) for a in parser._actions if isinstance(a, argparse._SubParsersAction)), {})


def _placeholder(word: str) -> bool:
    """A word that stands for a value: `<ID>`, `{}`, `[--flag]`, `$VAR`, `...`, or a metavar such as `PATH`."""
    return word.startswith(("<", "{", "[", "$", "...", "…")) or word.isupper()


def command_problems(text: str, parser: argparse.ArgumentParser | None = None) -> list[str]:
    """Each backticked `aidd <command> [--flag]` in `text` that the parser does not have: an unknown command or
    subcommand, or a flag that command does not take. A placeholder (`<ID>`, `{}`) is not checked, nor what follows a
    placeholder in a command's place; `a|b` is each of a and b."""
    parser = parser or cli_parser.build_parser()
    problems = []
    for m in AIDD_COMMAND.finditer(text):
        words = m.group(1).split()
        alternatives = [words]
        for i, w in enumerate(words[:2]):
            if "|" in w and not _placeholder(w):
                alternatives = [words[:i] + [alt] + words[i + 1 :] for alt in w.split("|")]
                break
        for words in alternatives:
            current, i = parser, 0
            while i < len(words) and (choices := _subcommands(current)):
                if _placeholder(words[i]):
                    current = None
                    break
                if words[i] not in choices:
                    problems.append(f"`aidd {m.group(1)}`: {current.prog} has no command {words[i]!r}")
                    current = None
                    break
                current, i = choices[words[i]], i + 1
            if current is None:
                continue
            positionals = [a for a in current._actions if not a.option_strings and not isinstance(a, argparse._SubParsersAction)]
            first, takes_value = None, False
            for word in words[i:]:
                if word == "--":
                    break
                if takes_value:  # the value of the flag before it, such as PATH in `--record PATH`
                    takes_value = False
                    continue
                flag = word.split("=")[0].rstrip(",;:.)")
                if re.fullmatch(r"--?[A-Za-z][\w-]*", flag):
                    action = current._option_string_actions.get(flag)
                    if action is None:
                        problems.append(f"`aidd {m.group(1)}`: {current.prog} takes no {flag}")
                    takes_value = action is not None and action.nargs != 0 and "=" not in word
                elif first is None:
                    first = word
            if positionals and positionals[0].choices and first and not _placeholder(first) and first not in positionals[0].choices:
                problems.append(f"`aidd {m.group(1)}`: {current.prog} takes no {first!r}")
    return problems


def message_strings(package: str) -> list[tuple[str, str]]:
    """(where, text) of every string in a package's source; an f-string with `{}` for each value it formats."""
    out = []
    for path in sorted((ROOT / "src" / "aidd" / package).rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parts = {id(v) for node in ast.walk(tree) if isinstance(node, ast.JoinedStr) for v in node.values}
        for node in ast.walk(tree):
            if id(node) in parts:
                continue
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                text = node.value
            elif isinstance(node, ast.JoinedStr):
                text = "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in node.values)
            else:
                continue
            out.append((f"{path.relative_to(ROOT).as_posix()}:{node.lineno}", text))
    return out


def rulebook_fixes() -> list[tuple[str, str]]:
    """Each rulebook row's fix, and each code's own fix, with the row's name."""
    return [(rule.name, fix) for rule in rulebook.RULES for fix in (rule.fix, *rule.fixes.values())]


def rulebook_fix_problems() -> list[str]:
    return [f"{name}: {p}: {fix}" for name, fix in rulebook_fixes() for p in fix_problems(fix)]


def source_command_problems() -> list[str]:
    """Every unknown command or flag named in a rulebook fix or in the source of the gate's findings and fixes, the
    guard's denials, and the work-item checks behind `aidd validate`."""
    parser = cli_parser.build_parser()
    bad = [f"rulebook {name}: {p}" for name, fix in rulebook_fixes() for p in command_problems(fix, parser)]
    for package in ("gate", "guard", "workitems"):
        bad += [f"{where}: {p}" for where, text in message_strings(package) for p in command_problems(text, parser)]
    return bad


class MessageChecksTests(unittest.TestCase):
    """The checks this file holds every message to, and proof that each one bites."""

    def test_every_rulebook_fix_names_something_to_act_on(self):
        self.assertEqual(rulebook_fix_problems(), [])

    def test_every_aidd_command_a_fix_denial_or_validate_message_names_is_real(self):
        self.assertEqual(source_command_problems(), [])

    def test_the_checks_bite(self):
        self.assertFalse(has_next_step("Agents never approve. Stop."))
        self.assertFalse(has_next_step("agents never merge; use it."))
        self.assertTrue(has_next_step("Agents never approve. Stop, and ask an Approver."))
        self.assertFalse(has_next_step("`aidd approve`: agents never approve. Stop."))
        self.assertTrue(has_next_step("Stop; `aidd gate --paths` gives the route."))
        self.assertTrue(fix_problems("Agents never approve. Stop."))
        self.assertTrue(fix_problems("report it with the context JSON; the gate fails closed"))
        self.assertEqual(fix_problems("ask the commander"), [])
        self.assertEqual(fix_problems("run `aidd gate --paths` again"), [])
        self.assertTrue(command_problems("run `aidd frobnicate` first"))
        self.assertTrue(command_problems("run `aidd validate --frobnicate`"))
        self.assertTrue(command_problems("run `aidd new frobnicate <topic>`"))
        self.assertTrue(command_problems("`aidd autopilot start|frobnicate`"))
        self.assertEqual(command_problems('`aidd new spec <ID> --title "..."`, then `aidd hash specs/<ID>.md`'), [])
        self.assertEqual(command_problems("`aidd new {} <topic> --spec {}` and `aidd test -- pytest -k x`"), [])
        # A rulebook row, a guard denial, and a validate message with filler and a made-up command each fail.
        filler = dataclasses.replace(rulebook.RULES[0], name="filler", fix="Agents never approve. Stop.")
        made_up = dataclasses.replace(rulebook.RULES[0], name="made_up", fix="run `aidd frobnicate`")
        with mock.patch.object(rulebook, "RULES", (*rulebook.RULES, filler, made_up)):
            self.assertEqual({p.split(":")[0] for p in rulebook_fix_problems()}, {"filler"})
            self.assertEqual({p.split(":")[0] for p in source_command_problems()}, {"rulebook made_up"})
        with mock.patch.object(verdicts, "TELL_A_PERSON", "Stop."):
            self.assertFalse(has_next_step(f"`gh pr merge`: agents never merge. {verdicts.TELL_A_PERSON}"))
        self.assertTrue(command_problems("error: specs/S-1.md: run `aidd frobnicate` and fix it"))


class GateFindingsTests(unittest.TestCase):
    def test_every_rulebook_row_has_a_fix(self):
        for rule in rulebook.RULES:
            with self.subTest(rule.name):
                self.assertTrue(rule.fix.strip())

    def test_the_gate_source_never_words_a_fix_itself(self):
        """Each `add(rule, level, message, fix)` in the gate leaves the wording to the rulebook: it passes no fix, so the
        finding takes its code's, or one `rulebook.finding_fix` built with this finding's specifics. A fix worded in
        the source would be a second owner of that next step (tests/test_gate_rules.py, FixOwnerTests)."""
        worded = []
        for path in sorted((ROOT / "src" / "aidd" / "gate").rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Call) or len(node.args) < 3:
                    continue
                name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
                if name != "add":
                    continue
                fix = node.args[3] if len(node.args) > 3 else next((k.value for k in node.keywords if k.arg == "fix"), None)
                if isinstance(fix, (ast.Constant, ast.JoinedStr)) or (isinstance(fix, ast.BinOp) and isinstance(fix.left, (ast.Constant, ast.JoinedStr))):
                    worded.append(f"{path.relative_to(ROOT)}:{node.lineno}")
        self.assertEqual(worded, [])

    def test_every_finding_the_examples_raise_has_a_fix(self):
        """The conformance suite, with its mutations: no failing or pending finding comes without a fix."""
        missing = set()
        for case in sorted(p for p in (ROOT / "examples").iterdir() if (p / "context.json").is_file()):
            ctx, _ = examples.load_example(case)
            runs = [copy.deepcopy(ctx)]
            for m in sorted((case / "mutations").glob("*.json")) if (case / "mutations").is_dir() else []:
                runs.append(examples.apply_ops(copy.deepcopy(ctx), json.loads(m.read_text(encoding="utf-8"))["ops"]))
            for c in runs:
                for f in gate.decide(c).findings:
                    if f.level != "warn" and not f.fix.strip():
                        missing.add(f"{case.name}: {f.code}")
                    missing.update(f"{case.name}: {f.code}: {p}" for p in command_problems(f"{f.message} {f.fix}"))
        self.assertEqual(sorted(missing), [])

    def test_a_policy_finding_without_a_fix_gets_one(self):
        from helpers import example

        ctx = example("02-normal-feature")
        ctx["policy"] = {"result": "allow", "findings": [{"rule": "r1", "level": "fail", "message": "no Friday deploys"}]}
        found = [f for f in gate.decide(ctx).findings if f.rule == "policy:r1"]
        self.assertTrue(found and all(f.fix for f in found), found)


@unittest.skipUnless(shutil.which("git"), "git is required")
class GuardDenialTests(unittest.TestCase):
    HELD = (
        '\nguard:\n  held_commands:\n    - name: terraform apply\n      match: ["terraform apply*"]\n'
        '    - name: production deploy\n      environment: production\n      requires: RELEASE_APPROVAL\n      match: ["make prod*"]\n'
    )

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = make_repo(Path(cls.tmp.name).resolve() / "repo", "team", spec="02-normal-feature:specs/SPEC-220.md")
        cfg = cls.root / ".aidd" / "config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + cls.HELD, encoding="utf-8")
        git(cls.root, "add", "-A")
        git(cls.root, "commit", "-qm", "held commands and a Spec")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def assertNextStep(self, verdict):
        decision, reason = verdict
        self.assertEqual(decision, "deny", reason)
        self.assertTrue(has_next_step(reason), f"no next step in: {reason}")
        self.assertEqual(command_problems(reason), [])

    def command(self, text: str, role: str | None = None):
        event = {"tool_name": "Bash", "tool_input": {"command": text}}
        if role:
            event["agent_type"] = f"aidd-team:{role}"
        with mock.patch.dict(os.environ, {"RELEASE_APPROVAL": ""}):
            return command_check.check_command(str(self.root), str(self.root), text, event)

    def test_commands_that_approve_merge_or_ship(self):
        for text in (
            "gh pr merge 1",
            "gh pr review --approve 1",
            "gh api -X PUT repos/o/r/pulls/1/merge",
            "glab mr merge 1",
            "aidd approve spec specs/SPEC-220.md",
            "aidd land",
            "git commit -m '/aidd approve SPEC-220 abc'",
            "git push --force origin main",
            "git push origin :main",
        ):
            with self.subTest(text):
                self.assertNextStep(self.command(text))

    def test_a_scope_denial_names_the_one_next_step_and_who_takes_it(self):
        """Smart, not strict: the denial hands over the fix, the agent's own step first, then the word the person types."""
        decision, reason = check_edit(str(self.root), ".github/workflows/new.yml", None, "", "x")
        self.assertEqual(decision, "deny")
        self.assertIn("Next: add it to a Task's scope in the Spec, then ask the person to type `approve <ID>` again", reason)
        with tempfile.TemporaryDirectory() as tmp:
            bare = make_repo(Path(tmp).resolve() / "bare", "team")
            decision, reason = check_edit(str(bare), ".github/workflows/new.yml", None, "", "x")
        self.assertEqual(decision, "deny")
        self.assertIn("Next: write the Spec that covers it: `aidd new spec --paths .github/workflows/new.yml`", reason)
        self.assertIn("type `approve <ID>`", reason)

    def test_a_denied_approval_or_merge_claims_nothing_about_the_gate(self):
        """The guard denies `gh pr merge` whether or not the gate has passed, so its next step hands the decision to a
        person and never says the change is ready. An approval or a ship goes to the person's own dialog first."""
        self.assertEqual(verdicts.TELL_A_PERSON, "stop here, and tell a person this needs their decision")
        for text, handed in (
            ("gh pr merge 1", verdicts.TELL_A_PERSON),
            ("glab mr merge 1", verdicts.TELL_A_PERSON),
            ("gh pr review --approve 1", verdicts.APPROVE_IN_A_DIALOG),
            ("aidd land", verdicts.APPROVE_IN_A_DIALOG),
        ):
            with self.subTest(text):
                decision, reason = self.command(text)
                self.assertEqual(decision, "deny")
                self.assertIn(handed, reason)
                self.assertNotIn("ready", reason)

    def test_held_commands(self):
        for text in ("terraform apply", "make prod", "RELEASE_APPROVAL=CHG-1 make prod"):
            with self.subTest(text):
                self.assertNextStep(self.command(text))

    def test_shell_writes_the_guard_cannot_read_or_that_leave_a_role_area(self):
        for text, role in (
            ("echo x > $TARGET", "developer"),
            ("cat fix.patch | git apply", "developer"),
            ("echo x > docs/notes.md", "developer"),
            ("echo x > notes.md", "reviewer"),
            ("echo x > .aidd/evidence/preview/abc1234/artifacts.json", "reviewer"),
            ("echo x > src/app.py", "reviewer"),
        ):
            with self.subTest(text):
                self.assertNextStep(self.command(text, role))

    def test_a_read_only_role_lists_its_preview_through_aidd(self):
        # A read-only role never writes artifacts.json by hand: the deny names the command that writes it, which it may run.
        decision, reason = self.command("shasum -a 256 a1.png > .aidd/evidence/preview/abc1234/artifacts.json", "reviewer")
        self.assertEqual(decision, "deny")
        self.assertIn("`aidd record artifacts <head-sha>`", reason)
        self.assertNotIn("another role", reason)
        self.assertEqual(denial_log.reason_code(reason), "role_area")
        self.assertEqual(self.command("aidd record artifacts abc1234", "reviewer")[0], "allow")
        decision, reason = self.command("echo x > README.md", "reviewer")
        self.assertIn("the reviewer role is read-only and writes no file", reason)
        self.assertEqual(denial_log.reason_code(reason), "role_area")

    def test_edits(self):
        root = str(self.root)
        for rel, role in (
            ("src/app.py", "nobody"),
            ("README.md", "developer"),
            ("src/elsewhere/x.py", "developer"),
            (".github/workflows/ci.yml", "developer"),
            ("src/checkout/rate_limit/limiter.py", "verifier"),
            ("specs/SPEC-220.md", "sre"),
        ):
            with self.subTest(rel=rel, role=role):
                self.assertNextStep(check_edit(root, rel, role))

    def test_mcp_tools(self):
        for name, args in (
            ("mcp__github__merge_pull_request", {}),
            ("mcp__github__create_commit_status", {"state": "success"}),
            ("mcp__github__create_pull_request_review", {"event": "APPROVE"}),
            ("mcp__github__add_issue_comment", {"body": "/aidd approve SPEC-220 abc"}),
        ):
            with self.subTest(name):
                self.assertNextStep(mcp_tools.check_mcp_tool(name, args))

    def test_the_hook_when_it_cannot_check(self):
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"AIDD_HOOK_FAIL_CLOSED": "1"}), contextlib.chdir(self.root):  # an adopted repository, wherever the tests run
            pre_tool.pre_tool_hook(io.StringIO("not json"), out)
        reason = json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertTrue(has_next_step(reason), reason)
        self.assertTrue(has_next_step(verdicts.GUARD_BROKE))
        self.assertTrue(has_next_step(verdicts.TELL_A_PERSON))


@unittest.skipUnless(shutil.which("git"), "git is required")
class ValidateTests(unittest.TestCase):
    def run_validate(self, root: Path, *paths: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.chdir(root), redirect_stdout(out):
            code = app.main(["validate", *paths])
        self.assertEqual(command_problems(out.getvalue()), [])
        return code, out.getvalue()

    def test_each_error_names_its_file_and_the_summary_says_what_next(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d).resolve() / "repo", "team", spec="02-normal-feature:specs/SPEC-220.md")
            spec = root / "specs" / "SPEC-220.md"
            spec.write_text(spec.read_text(encoding="utf-8").replace("kind: spec", "kind: nonsense", 1), encoding="utf-8")
            (root / "specs" / "SPEC-221.md").write_text("---\nid: SPEC-221\nkind: spec\n---\n# A Spec with nothing in it\n", encoding="utf-8")
            code, text = self.run_validate(root)
        self.assertEqual(code, 1)
        errors = [line for line in text.splitlines() if line.startswith("error: ")]
        self.assertTrue(errors, text)
        for line in errors:
            with self.subTest(line):
                self.assertRegex(line, r"^error: (specs/SPEC-22[01]\.md|\.aidd/config\.toml)\b")
        self.assertTrue(text.rstrip().endswith("then run `aidd validate` again"), text)

    def test_no_config_says_how_to_adopt(self):
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q", "-b", "main")
            _, text = self.run_validate(Path(d))
        self.assertIn("run `aidd init`", text)

    def test_with_no_config_alone_the_summary_sends_you_to_init_not_to_a_file(self):
        """A missing config names no file to fix, so the summary sends you to `aidd init`, never round to validate."""
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q", "-b", "main")
            code, text = self.run_validate(Path(d))
        self.assertEqual(code, 1)
        summary = text.rstrip().splitlines()[-1]
        self.assertEqual(summary, "1 error(s), 0 warning(s): run `aidd init` to adopt this repository, then run `aidd validate` again")
        self.assertNotIn("file", summary)

    def test_with_no_config_and_a_broken_file_the_summary_names_both_steps(self):
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q", "-b", "main")
            (Path(d) / "specs").mkdir()
            (Path(d) / "specs" / "SPEC-1.md").write_text("---\nid: SPEC-1\nkind: nonsense\n---\n# Broken\n", encoding="utf-8")
            code, text = self.run_validate(Path(d))
        self.assertEqual(code, 1)
        self.assertIn("error: specs/SPEC-1.md", text)
        self.assertTrue(text.rstrip().endswith(": run `aidd init` to adopt this repository, fix each file named above, then run `aidd validate` again"), text)

    def test_the_summary_names_a_file_step_only_when_an_error_names_a_file(self):
        from aidd import workitems

        no_config = workitems.check_repo(Path(tempfile.gettempdir()) / "no-such-aidd-repo")[0]
        self.assertEqual(len(no_config), 1)
        self.assertIsNone(workitems.validate_next_step([]))
        self.assertNotIn("file", workitems.validate_next_step(no_config))
        self.assertIn("fix each file named above", workitems.validate_next_step(["specs/S-1.md: kind is not one of ..."]))
        self.assertIn("aidd init", workitems.validate_next_step([*no_config, "specs/S-1.md: kind is not one of ..."]))


if __name__ == "__main__":
    unittest.main()
