"""Fail closed: a rule aidd cannot read is an error, never an `allow`. An action no rule can name, a config rule that names
none, and a config that does not load each stop the command that decides, with why and the next step; every config
error names its line where the file holds one."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import test_delegation_check as check_fixture
from helpers import aidd_here, git

from aidd import __version__, config, delegation, risk
from aidd.cli import mcp_server
from aidd.kernel import json_schema
from aidd.delegation import answers, outcome  # noqa: F401  (the hook's check runs through these)
from aidd.config import extends

BASE = 'aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@a"]\n'
ACTIONS = sorted(risk.builtin()["actions"])


def repo(config_text: str | None = BASE) -> tempfile.TemporaryDirectory:
    """A git repository holding `config_text` as its config (none when None)."""
    tmp = tempfile.TemporaryDirectory()
    git(tmp.name, "init", "-q", "-b", "main")
    if config_text is not None:
        (Path(tmp.name) / ".aidd").mkdir()
        (Path(tmp.name) / ".aidd" / "config.yaml").write_text(config_text, encoding="utf-8")
    git(tmp.name, "add", "-A")
    git(tmp.name, "commit", "-q", "--allow-empty", "-m", "day 0")
    return tmp


class UnknownNameTests(unittest.TestCase):
    """For every action name that is no action, `aidd risk --action` exits 2 and names the closest action and the list."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = repo()
        cls.root = cls.tmp.name

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def risk(self, *args: str):
        return aidd_here("risk", *args, cwd=self.root)

    def test_every_built_in_action_is_answered(self):
        for action in ACTIONS:
            with self.subTest(action=action):
                done = self.risk("--action", action)
                self.assertEqual((done.returncode, done.stdout.startswith("level: ")), (0, True), done.stderr)

    def test_a_typo_of_every_action_is_an_error_that_names_the_action_it_looks_like(self):
        for action in ACTIONS:
            for typo in (action[:-1], action[:2] + action[3:], action[0].upper() + action[1:]):
                if typo in ACTIONS:
                    continue
                with self.subTest(typo=typo):
                    done = self.risk("--action", typo)
                    self.assertEqual(done.returncode, 2, done.stdout)
                    self.assertEqual(done.stdout, "")
                    self.assertIn("is not an action aidd knows", done.stderr)
                    self.assertIn("`aidd risk --list`", done.stderr)
                    self.assertIn(f"did you mean `{action}`?", done.stderr)

    def test_a_name_that_looks_like_nothing_still_names_where_the_list_is(self):
        for name in ("zzz", "spec.*", "*", "pr", "pr.", "PR.MERGE", " pr.merge"):
            with self.subTest(name=name):
                done = self.risk("--action", name)
                self.assertEqual((done.returncode, "`aidd risk --list`" in done.stderr), (2, True), done.stderr)

    def test_the_json_form_is_an_error_too(self):
        done = self.risk("--action", "pr.mrge", "--json")
        self.assertEqual(done.returncode, 2)
        error = json.loads(done.stdout)["error"]  # stdout holds the error object of every `--json` command, and stderr the words
        self.assertEqual(error["code"], "cli.invalid")
        self.assertIn("did you mean `pr.merge`?", error["message"])
        self.assertIn("did you mean `pr.merge`?", done.stderr)

    def test_an_area_or_a_role_that_is_none_is_an_error_not_the_general_level(self):
        for flags in (
            ("--action", "code.edit", "--area", "paymnts"),
            ("--action", "code.edit", "--role", "developr"),
            ("--command", "ls", "--role", "developr"),
        ):
            with self.subTest(flags=flags):
                done = self.risk(*flags)
                self.assertEqual((done.returncode, done.stdout), (2, ""), done.stderr)
                self.assertIn("did you mean", done.stderr)
        self.assertEqual(self.risk("--action", "code.edit", "--area", "payments", "--role", "developer").returncode, 0)

    def test_a_role_a_rule_in_force_names_is_a_role(self):
        text = BASE + "risks:\n  rules:\n    - {action: pr.merge, role: qa, level: report}\n"
        with repo(text) as root:
            for flags in (("--action", "pr.merge", "--role", "qa"), ("--command", "gh pr merge 1", "--role", "qa")):
                with self.subTest(flags=flags):
                    done = aidd_here("risk", *flags, cwd=root)
                    self.assertEqual(done.returncode, 0, done.stderr)
            done = aidd_here("risk", "--action", "pr.merge", "--role", "qaa", cwd=root)
            self.assertEqual(done.returncode, 2)
            self.assertIn("did you mean `qa`", done.stderr)

    def test_the_mcp_tool_answers_an_unknown_action_as_a_tool_error(self):
        is_error, text = mcp_server.call("risk", {"action": "pr.mrge"}, self.root)
        self.assertTrue(is_error, text)
        self.assertIn("did you mean `pr.merge`?", text)
        self.assertEqual(mcp_server.call("risk", {"action": "pr.merge"}, self.root)[0], False)

    def test_an_action_the_config_defines_is_known(self):
        defined = (
            BASE
            + 'risks:\n  actions:\n    acme.release:\n      description: Ship it.\n      commands: ["acme ship*"]\n  rules:\n    - {action: acme.release, level: ask}\n'
        )
        with repo(defined) as root:
            done = aidd_here("risk", "--action", "acme.release", cwd=root)
            self.assertEqual((done.returncode, done.stdout.startswith("level: ask")), (0, True), done.stderr)
            self.assertEqual(aidd_here("risk", "--command", "acme ship it", cwd=root).returncode, 0)

    def test_a_command_never_reads_as_an_action_aidd_does_not_know(self):
        """`--command` finds actions only among the ones in force, so a command is never an unknown action."""
        rs = risk.rule_set(None)
        for action, spec in rs.actions.items():
            for example in spec.get("examples") or []:
                with self.subTest(example=example):
                    found = {a["action"] for a in risk.command_level(rs, example, cwd=None)["actions"]}
                    self.assertTrue(found <= set(rs.actions), (action, found))

    def test_the_delegate_never_passes_an_action_it_does_not_know(self):
        with tempfile.TemporaryDirectory() as d:
            fixture = check_fixture.Repo(Path(d).resolve())
            head = fixture.change()
            result = fixture.check(head, action="pr.mrge")
            self.assertNotEqual(result["outcome"], "eligible")


class RuleActionTests(unittest.TestCase):
    """A config rule that names no action is a config error that names the file and the line; a prefix rule is not."""

    def load(self, rules: str, extra: str = ""):
        return BASE + "risks:\n" + extra + "  rules:\n" + rules

    def test_a_rule_for_an_action_no_layer_defines_fails_the_load_at_its_line(self):
        for action, closest in (("pr.opn", "pr.open"), ("git.push.forse", "git.push.force"), ("acme.go", None), ("spec.aprove", "spec.approve")):
            with self.subTest(action=action):
                text = self.load(f"    - {{action: pr.open, level: report}}\n    - {{action: {action}, level: ask}}\n")
                with self.assertRaises(config.ConfigError) as caught:
                    config.load_text(text)
                line = text.splitlines().index(f"    - {{action: {action}, level: ask}}") + 1
                message = str(caught.exception)
                self.assertIn(f"line {line}: ", message)
                self.assertIn(f"$.risks.rules[1].action: '{action}' is no action aidd knows", message)
                self.assertIn("`aidd risk --list`", message)
                self.assertIn("risks.actions", message)
                if closest:
                    self.assertIn(f"did you mean `{closest}`", message)

    def test_a_config_written_for_a_newer_aidd_says_so_and_names_the_two_ways_out(self):
        """An action only a newer aidd knows still fails the load, because aidd cannot tell it from a typo."""
        ahead = 'aidd_version: "1.9.0"\nprofile: team\nrisks:\n  rules:\n    - {action: pr.from_the_future, level: ask}\n'
        with repo(ahead) as root:
            for args in (("risk", "--action", "pr.open"), ("validate",)):
                with self.subTest(args=args):
                    done = aidd_here(*args, cwd=root)
                    said = done.stdout + done.stderr
                    self.assertNotEqual(done.returncode, 0)
                    self.assertIn("'pr.from_the_future' is no action aidd knows", said)
                    self.assertIn(f"was written for aidd 1.9.0, while this is aidd {__version__}", said)
                    self.assertIn("Upgrade aidd to 1.9.0", said)
                    self.assertIn("move the pin to 1.9.0", said)
        for text, why in (
            (ahead.replace("1.9.0", "1.0.0"), "the same version: a typo"),
            (ahead.replace("1.9.0", "0.9.0"), "an older config"),
            (ahead.replace("pr.from_the_future", "pr.open"), "a newer config that loads says nothing"),
        ):
            with self.subTest(why=why), repo(text) as root:
                said = aidd_here("validate", cwd=root)
                self.assertNotIn("was written for aidd", said.stdout + said.stderr)

    def test_a_prefix_a_star_and_an_action_the_config_defines_are_valid(self):
        extra = '  actions:\n    acme.go:\n      description: Go.\n      commands: ["acme go*"]\n'
        text = self.load(
            '    - {action: "spec.*", level: ask}\n    - {action: "*", level: report}\n    - {action: acme.go, level: ask}\n    - {action: "acme.*", level: ask}\n',
            extra,
        )
        self.assertEqual(config.load_text(text).profile, "team")

    def test_a_prefix_that_covers_no_action_is_an_error(self):
        with self.assertRaises(config.ConfigError) as caught:
            config.load_text(self.load('    - {action: "acmee.*", level: ask}\n'))
        self.assertIn("no action aidd knows", str(caught.exception))

    def test_a_rule_a_parent_sets_names_the_parent(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "base.yaml").write_text(BASE + "risks:\n  rules:\n    - {action: pr.opn, level: ask}\n", encoding="utf-8")
            text = BASE + "extends:\n  - path: base.yaml\n"
            with self.assertRaises(config.ConfigError) as caught:
                config.load_file("child.yaml", d, text=text)
            self.assertTrue(str(caught.exception).startswith("preset base.yaml: "), str(caught.exception))
            self.assertIn("pr.opn", str(caught.exception))

    def test_a_child_may_define_the_action_a_parent_rule_names(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "base.yaml").write_text(BASE + "risks:\n  rules:\n    - {action: acme.go, level: ask}\n", encoding="utf-8")
            text = BASE + 'extends:\n  - path: base.yaml\nrisks:\n  actions:\n    acme.go:\n      description: Go.\n      commands: ["acme go*"]\n'
            self.assertEqual(config.load_file("child.yaml", d, text=text).profile, "team")

    def test_the_built_in_rules_name_only_known_actions(self):
        known = set(ACTIONS)
        for rule in risk.builtin()["rules"]:
            self.assertTrue(any(config.action_matches(rule["action"], a) for a in known), rule)


class UnreadableConfigTests(unittest.TestCase):
    """A config aidd cannot read stops every command that decides, and the views show the problem first and exit 1."""

    BROKEN = BASE + "\nbogus_key: 1\n"
    LINE = f"line {len(BROKEN.splitlines())}: "

    @classmethod
    def setUpClass(cls):
        cls.tmp = repo(cls.BROKEN)
        cls.root = cls.tmp.name

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_each_command_that_decides_stops_with_the_error_and_the_next_step(self):
        for args in (
            ("risk", "--paths", "src/app.py"),
            ("risk", "--action", "pr.merge"),
            ("risk", "--command", "git push"),
            ("risk", "--list"),
            ("risk", "--suggest"),
            ("test",),
            ("new", "spec", "SPEC-1", "--title", "A spec"),
            ("standard", "add", "python/ruff-lint-format"),
        ):
            with self.subTest(args=args):
                done = aidd_here(*args, cwd=self.root)
                self.assertEqual((done.returncode, done.stdout), (2, ""), done.stderr)
                self.assertIn(f".aidd/config.yaml: {self.LINE}$: unknown field 'bogus_key'", done.stderr)
                self.assertIn("run `aidd validate`", done.stderr)
                self.assertIn("cannot read the rules", done.stderr)

    def test_the_mcp_tools_stop_the_same_way(self):
        for args in ({"paths": ["src/app.py"]}, {"action": "pr.merge"}, {"command": "git push"}):
            with self.subTest(args=args):
                is_error, text = mcp_server.call("risk", args, self.root)
                self.assertTrue(is_error)
                self.assertIn("run `aidd validate`", text)

    def test_the_mcp_views_report_the_problem_as_the_cli_does(self):
        """`validate` is an error with the config's error named; `status` and `recall` lead with the problem."""
        is_error, text = mcp_server.call("validate", {}, self.root)
        self.assertTrue(is_error, text)
        self.assertIn(f".aidd/config.yaml: {self.LINE}$: unknown field 'bogus_key'", text)
        for name, args in (("status", {}), ("status", {"all_branches": True}), ("recall", {"words": "word"})):
            with self.subTest(tool=name, args=args):
                is_error, text = mcp_server.call(name, args, self.root)
                self.assertFalse(is_error, "a view shows what it can, and exits 1")
                self.assertTrue(text.startswith("aidd: .aidd/config.yaml does not load"), text[:200])
                self.assertIn("`aidd validate`", text.splitlines()[0])

    def test_the_mcp_views_of_a_config_that_loads_are_not_errors_and_lead_with_the_answer(self):
        with repo() as root:
            self.assertEqual(mcp_server.call("validate", {}, root)[0], False)
            for name, args in (("status", {}), ("recall", {"words": "word"})):
                is_error, text = mcp_server.call(name, args, root)
                self.assertEqual((is_error, text.startswith("{")), (False, True), text[:200])

    def test_a_bug_while_reading_the_config_is_not_taken_for_a_config_that_does_not_load(self):
        from unittest import mock

        from aidd.workitems import repo_reads

        with repo() as root, mock.patch("aidd.kernel.documents.parse_yaml", side_effect=TypeError("a bug")):
            with self.assertRaises(TypeError):
                repo_reads.config_at(Path(root))

    def test_validate_of_a_path_reports_the_config_that_does_not_load_and_fails(self):
        """The form an agent uses before it asks for Spec approval: a Spec checked by rules it cannot read never passes."""
        with repo(self.BROKEN) as root:
            (Path(root) / "specs").mkdir()
            (Path(root) / "specs" / "SPEC-1.md").write_text("# no front matter\n", encoding="utf-8")
            for args in (("validate", "specs/SPEC-1.md"), ("validate", "--json", "specs/SPEC-1.md")):
                with self.subTest(args=args):
                    done = aidd_here(*args, cwd=root)
                    self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                    self.assertIn(f".aidd/config.yaml: {self.LINE}$: unknown field 'bogus_key'", done.stdout)
            is_error, text = mcp_server.call("validate", {"paths": ["specs/SPEC-1.md"]}, root)
            self.assertTrue(is_error, text)
            self.assertIn("unknown field 'bogus_key'", text)
        with repo(BASE) as root:  # a config that loads adds nothing
            (Path(root) / "specs").mkdir()
            (Path(root) / "specs" / "SPEC-1.md").write_text("# no front matter\n", encoding="utf-8")
            self.assertNotIn(".aidd/config.yaml", aidd_here("validate", "specs/SPEC-1.md", cwd=root).stdout)

    def test_a_parent_url_that_is_no_url_is_a_config_error_for_every_command(self):
        """`urlsplit` raises a bare ValueError ("Invalid IPv6 URL"); it must reach the person as the config's error."""
        text = BASE + f'extends:\n  - {{url: "https://[::1/x.yaml", sha256: "{"a" * 64}"}}\n'
        with repo(text) as root:
            for args in (("risk", "--action", "pr.merge"), ("status",), ("recall", "word"), ("explain", "pr.merge"), ("validate",)):
                with self.subTest(args=args):
                    done = aidd_here(*args, cwd=root)
                    said = done.stdout + done.stderr
                    self.assertNotEqual(done.returncode, 0, said)
                    self.assertIn(".aidd/config.yaml: line 6: extends url 'https://[::1/x.yaml' is not a URL (Invalid IPv6 URL)", said)
                    self.assertIn("aidd validate", said)
                    self.assertNotIn("Traceback", said)

    def test_collecting_the_parents_of_a_url_that_is_no_url_warns_and_does_not_raise(self):
        text = BASE + f'extends:\n  - {{url: "https://[::1/x.yaml", sha256: "{"a" * 64}"}}\n'
        warnings: list[str] = []
        found = extends.collect_extends(text, None, lambda url: b"", {}, warnings=warnings)
        self.assertEqual(found, {})
        self.assertTrue(any("is not a URL" in w for w in warnings), warnings)

    def test_a_view_shows_the_problem_first_and_exits_1(self):
        for args in (("status",), ("status", "--all-branches"), ("recall", "word"), ("explain", "pr.merge")):
            with self.subTest(args=args):
                done = aidd_here(*args, cwd=self.root)
                self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                self.assertTrue(done.stderr.startswith("aidd: .aidd/config.yaml does not load"), done.stderr)
                self.assertIn("`aidd validate`", done.stderr)

    def test_doctor_puts_the_problem_first_and_exits_1(self):
        done = aidd_here("doctor", "--json", cwd=self.root)
        self.assertEqual(done.returncode, 1)
        shown = json.loads(done.stdout)
        self.assertEqual(json_schema.validate(shown, "doctor.schema.json"), [])
        checks = shown["checks"]
        self.assertEqual(checks[0]["result"], "fail")
        self.assertIn("config:", checks[0]["message"])
        self.assertIn("run `aidd validate`", checks[0]["message"])
        # Rules it cannot read are not checked, never reported as fine.
        self.assertFalse(any("risk rules:" in c["message"] and c["result"] == "ok" for c in checks))

    def test_a_missing_config_is_not_a_broken_one(self):
        with repo(None) as root:
            self.assertEqual(aidd_here("status", cwd=root).returncode, 0)
            self.assertEqual(aidd_here("risk", "--action", "pr.merge", cwd=root).returncode, 0)

    def test_the_delegate_defers_on_a_tip_config_it_cannot_read(self):
        with tempfile.TemporaryDirectory() as d:
            fixture = check_fixture.Repo(Path(d).resolve())
            head = fixture.change()
            fixture.write(".aidd/config.yaml", check_fixture.config_text() + "\nbogus_key: 1\n")
            fixture.commit("break the config on main")
            result = fixture.check(head)
            self.assertEqual(result["outcome"], "defer")
            self.assertIn("config_unreadable", check_fixture.codes(result))

    def test_the_hook_gives_no_decision_on_a_config_it_cannot_read(self):
        with tempfile.TemporaryDirectory() as d:
            fixture = check_fixture.Repo(Path(d).resolve())
            head = fixture.change()
            command = fixture.check(head)["covers"]["command"]
            ask = delegation.Request(action="git.merge", command=command, head=head, cwd=d, env=check_fixture.ENV)
            delegation.answer(ask, "accept", "green and in scope")
            event = {"hook_event_name": "PermissionRequest", "tool_name": "Bash", "tool_input": {"command": command}, "cwd": d}
            self.assertIn("allow", answers.hook_main(json.dumps(event, sort_keys=True)), "with a readable config the hook allows it")
            fixture.write(".aidd/config.yaml", check_fixture.config_text() + "\nbogus_key: 1\n")
            fixture.commit("break the config on main")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(answers.hook_main(json.dumps(event)), "")
            self.assertIn("config_unreadable", err.getvalue())
            self.assertIn("the prompt stays", err.getvalue())


class ConfigLineTests(unittest.TestCase):
    """Every config error that names a place in the file names its line."""

    def rejected(self, text: str, where: str = ".aidd/config.yaml", **kw) -> str:
        with self.assertRaises(config.ConfigError) as caught:
            config.load_text(text, where=where, **kw)
        return str(caught.exception)

    def test_each_kind_of_error_names_the_line_of_the_key(self):
        cases = [
            # (what is wrong, the text added to BASE, the key's line within it, a word of the message)
            ("an unknown top-level key", "\nbogus_key: 1\n", 2, "unknown field 'bogus_key'"),
            ("a near-miss top-level key", '\nownres:\n  approvers: ["@b"]\n', 2, "unknown field 'ownres'"),
            ("an unknown nested key", "\nrisks:\n  areas:\n    x:\n      pathss: [a]\n", 5, "unknown field 'pathss'"),
            ("a bad enum", "\nproject:\n  work: clients\n", 3, "must be one of"),
            ("a mistyped lock", "\nlocks: [projct]\n", 2, "did you mean `project`"),
            ("a wrong type", "\ntests: npm test\n", 2, "expected array"),
            ("a bad enum in a sequence item", "\nrisks:\n  rules:\n    - {action: pr.open, level: alow}\n", 4, "must be one of allow, report, ask"),
            ("a missing required field", "\nrisks:\n  rules:\n    - action: pr.open\n", 4, "missing required field 'level'"),
            ("an unknown key in a block item", "\nrisks:\n  rules:\n    - action: pr.open\n      level: ask\n      levl: ask\n", 6, "unknown field 'levl'"),
            (
                "a route on the wrong action",
                "\nrisks:\n  rules:\n    - {action: pr.open, level: ask, route: major}\n",
                4,
                "only `spec.approve` takes a `route`",
            ),
            ("a folder that is the repository's top", '\nspecs_dir: "."\n', 2, "does not match"),
            (
                "a delivery team with no such harness",
                '\ndelivery_teams:\n  web:\n    approvers: ["@a"]\n    areas: [auth]\n    harness: nope\n',
                6,
                "is no harness aidd knows",
            ),
            ("an industry id in a policy", "\nstandards_policy:\n  require: [owasp-asvs]\n", 3, "industry standard"),
            ("a rule for no action", "\nrisks:\n  rules:\n    - {action: pr.opn, level: ask}\n", 4, "no action aidd knows"),
            ("a parent that is not there", "\nextends:\n  - path: missing.yaml\n", 3, "not found"),
        ]
        for name, added, offset, word in cases:
            with self.subTest(name):
                text = BASE + added
                first = len(BASE.splitlines())
                message = self.rejected(text, read=lambda p: None)
                self.assertIn(f"line {first + offset}: ", message)
                self.assertIn(word, message)

    def test_a_yaml_error_names_its_line(self):
        with self.assertRaises(Exception) as caught:
            config.load_text(BASE + "\nrisks: [unclosed\n")
        self.assertIn("line 6", str(caught.exception))

    def test_a_parent_file_names_its_own_line(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "base.yaml").write_text(BASE + "\nbogus_key: 1\n", encoding="utf-8")
            with self.assertRaises(config.ConfigError) as caught:
                config.load_file("child.yaml", d, text=BASE + "extends:\n  - path: base.yaml\n")
            self.assertTrue(str(caught.exception).startswith("base.yaml: line 6: "), str(caught.exception))

    def test_several_errors_each_name_their_line(self):
        message = self.rejected(BASE + "\nbogus: 1\nlocks: [projct]\n")
        self.assertEqual(len(message.splitlines()), 2)
        self.assertEqual([line.split(": ")[1] for line in message.splitlines()], ["line 6", "line 7"])

    def test_a_problem_after_the_parents_merged_names_no_line_it_cannot_know(self):
        """A line is named only where this file holds the key: an error found in the merged result names the file alone."""
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "base.yaml").write_text(BASE + 'specs_dir: "."\n', encoding="utf-8")
            with self.assertRaises(config.ConfigError) as caught:
                config.load_file("child.yaml", d, text=BASE + "extends:\n  - path: base.yaml\n")
            self.assertTrue(str(caught.exception).startswith("base.yaml: line 5: "), str(caught.exception))


class KeyLinesTests(unittest.TestCase):
    """`strict_yaml.key_lines` marks the same lines the parser reads, for every shape the subset has."""

    TEXT = (
        "# a comment\n"  # 1
        "a: 1\n"  # 2
        "b:\n"  # 3
        "  - x: 1\n"  # 4
        "    v: 2\n"  # 5
        "  - {z: 3}\n"  # 6
        "  - plain\n"  # 7
        "c:\n"  # 8
        "  d:\n"  # 9
        "    - [1, 2]\n"  # 10
        "  e: |\n"  # 11
        "    text\n"  # 12
        "f: [1,\n"  # 13
        "  2]\n"  # 14
        "g: 3\n"  # 15
    )

    def test_each_path_has_its_line(self):
        from aidd.kernel import strict_yaml

        marks = strict_yaml.key_lines(self.TEXT)
        for path, line in {
            "$.a": 2, "$.b": 3, "$.b[0]": 4, "$.b[0].x": 4, "$.b[0].v": 5, "$.b[1]": 6, "$.b[2]": 7, "$.c.d": 9, "$.c.d[0]": 10, "$.c.e": 11, "$.f": 13, "$.g": 15,
        }.items():  # fmt: skip
            with self.subTest(path=path):
                self.assertEqual(strict_yaml.line_of(marks, path), line)
        self.assertEqual(strict_yaml.line_of(marks, "$.b[1].z"), 6, "inside a flow collection: the line it starts on")
        self.assertEqual(strict_yaml.line_of(marks, "$.aa"), None)
        self.assertEqual(strict_yaml.line_of(marks, "$.a.b"), 2, "the nearest path above")

    def test_a_document_the_parser_refuses_has_no_lines(self):
        from aidd.kernel import strict_yaml

        self.assertEqual(strict_yaml.key_lines("a: [unclosed\n"), {})


if __name__ == "__main__":
    unittest.main()
