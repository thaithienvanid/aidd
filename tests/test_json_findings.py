"""Problems in `--json` output come in one shape (`finding` in the common schema), and a `--json` command that stops with exit
2 prints one error object (`error`) on stdout, with the same words on stderr as before.

- every `--json` command that ends in exit 2 prints an error object whose code is in `schemas/findings.json`, and its
  stderr and exit code are those of the same call without `--json`;
- `validate`, `doctor`, and `status` print `findings` beside their text lists, each list line the message of one finding, so
  the two never disagree;
- `aidd explain <code>` answers each code of the registry, and an unknown code names the closest one;
- the MCP tools return the objects the CLI prints."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import SAMPLE_SPEC, git, make_repo

from aidd import config
from aidd.cli import app, mcp_server, parser
from aidd.kernel import findings, json_schema
from aidd.kernel import git as kgit
from aidd.kernel import http as khttp

URN = "urn:aidd:1:common#/$defs/"


def run(cwd: Path, *argv: str) -> tuple[int, str, str]:
    """`aidd <argv>` in this process from `cwd`: its exit code, its stdout, and its stderr."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.chdir(cwd), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = app.main(list(argv))
        except SystemExit as stop:
            code = stop.code if isinstance(stop.code, int) else 2
    return code, out.getvalue(), err.getvalue()


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = make_repo(Path(cls.tmp.name) / "repo", "team", spec="specs/SPEC-220.md")
        # A file that breaks its schema gives errors, and the sample Spec gives warnings or notes of its own.
        (cls.root / "specs" / "BAD.md").write_text("---\ntype: spec\nid: BAD\nbogus: 1\n---\n\n# x\n", encoding="utf-8")
        # A planned Spec, whose Tasks still hold placeholders, gives a note; a Spec with a leftover placeholder gives a warning.
        planned = (
            SAMPLE_SPEC.replace("SPEC-220", "SPEC-230").replace('scope: ["src/checkout/"]', 'scope: ["TODO"]').replace("Apply the discount at checkout", "TODO")
        )
        (cls.root / "specs" / "SPEC-230.md").write_text(planned.replace('files: ["tests/test_discount.py"]', 'files: ["TODO"]'), encoding="utf-8")
        (cls.root / "specs" / "SPEC-221.md").write_text(
            SAMPLE_SPEC.replace("SPEC-220", "SPEC-221").replace("## Design\n\nOne function", "## Design\n\nTODO: One function"), encoding="utf-8"
        )


class ErrorObjectTests(Fixture):
    """Each case is a call that ends in exit 2, and the code its error object must carry."""

    CASES = (
        ("an unknown command", ("frobnicate", "--json"), "cli.bad_arguments"),
        ("an unknown option", ("risk", "--nope", "--json"), "cli.bad_arguments"),
        ("a value that is no choice", ("risk", "--action", "code.edit", "--branch", "nowhere", "--json"), "cli.bad_arguments"),
        ("a missing mode", ("risk", "--json"), "cli.invalid"),
        ("an action that is none", ("risk", "--action", "pr.mrge", "--json"), "cli.invalid"),
        ("no word to explain", ("explain", "--json"), "cli.invalid"),
        ("a file that is not there", ("validate", "specs/NOT-THERE.md", "--json"), "cli.file_unreadable"),
        ("an id that names no work item", ("status", "SPEC-9999", "--json"), "cli.invalid"),
    )

    def test_every_json_command_that_stops_prints_an_error_object_and_keeps_its_words_on_stderr(self):
        for what, argv, code in self.CASES:
            with self.subTest(what):
                exit_code, out, err = run(self.root, *argv)
                plain_code, plain_out, plain_err = run(self.root, *(a for a in argv if a != "--json"))
                self.assertEqual((exit_code, plain_code), (2, 2), "the exit code stays 2")
                shown = json.loads(out)
                self.assertEqual(json_schema.validate(shown, URN + "error"), [])
                self.assertEqual(shown["error"]["code"], code)
                self.assertIn(shown["error"]["code"], findings.codes(), "the registry holds the code")
                self.assertEqual(err, plain_err, "the words for a person are the same with and without --json")
                self.assertEqual(plain_out, "", "without --json nothing goes to stdout")

    def test_the_message_is_the_stderr_text(self):
        _, out, err = run(self.root, "risk", "--action", "pr.mrge", "--json")
        self.assertEqual(err, f"aidd: {json.loads(out)['error']['message']}\n")

    def test_a_folder_in_no_repository_is_named_for_what_it_is(self):
        with tempfile.TemporaryDirectory() as bare:
            code, out, err = run(Path(bare), "status", "--json")
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(out)["error"]["code"], "cli.no_repository")
            self.assertIn("git init", err)

    def test_a_config_that_does_not_load_is_the_configs_code(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d) / "repo", "team")
            (root / ".aidd" / "config.yaml").write_text("profile: [unclosed\n", encoding="utf-8")
            code, out, _ = run(root, "risk", "--paths", "a.py", "--json")
            self.assertEqual(code, 2)
            error = json.loads(out)["error"]
            self.assertEqual((error["code"], error["path"]), ("config.unreadable", ".aidd/config.yaml"))

    def test_an_unknown_word_keeps_its_empty_matches_and_adds_the_error(self):
        code, out, _ = run(self.root, "explain", "flibbertigibbet", "--json")
        shown = json.loads(out)
        self.assertEqual((code, shown["matches"], shown["error"]["code"]), (2, [], "cli.unknown_word"))
        self.assertEqual(json_schema.validate(shown, "explain.schema.json"), [])

    def test_a_crash_is_an_internal_error_and_each_exception_class_has_its_code(self):
        classes = (
            (ValueError("v"), "cli.invalid"),
            (OSError("o"), "cli.file_unreadable"),
            (LookupError("l"), "cli.not_found"),
            (RuntimeError("r"), "cli.failed"),
            (kgit.GitError("fatal: bad revision"), "cli.git_failed"),
            (kgit.GitError("fatal: not a git repository"), "cli.no_repository"),
            (khttp.HttpError(503, "https://example.com/x?token=s", "down"), "cli.network_failed"),
            (config.ConfigUnreadable("config says no"), "config.unreadable"),
            (ZeroDivisionError("z"), "cli.internal_error"),
        )
        real = parser.build_parser
        for error, code in classes:
            with self.subTest(type(error).__name__):

                def boom(_args, error=error):
                    raise error

                def build(error=error, boom=boom, **kw):
                    p = real(**kw)
                    p._subparsers._group_actions[0].choices["doctor"].set_defaults(func=boom)
                    return p

                with mock.patch.object(parser, "build_parser", build), mock.patch.dict(os.environ, {"AIDD_DEBUG": "0"}):
                    exit_code, out, _ = run(self.root, "doctor", "--json")
                self.assertEqual((exit_code, json.loads(out)["error"]["code"]), (2, code))

    def test_a_failed_check_is_not_an_error_object(self):
        """Exit 1 is a result, so `validate` prints its own output and no `error` key."""
        code, out, _ = run(self.root, "validate", "--json")
        self.assertEqual(code, 1)
        self.assertNotIn("error", json.loads(out))


class FindingListTests(Fixture):
    def test_validate_gives_one_finding_for_each_line_of_its_lists_with_the_same_message(self):
        code, out, _ = run(self.root, "validate", "--json")
        shown = json.loads(out)
        self.assertEqual(json_schema.validate(shown, "validate.schema.json"), [])
        self.assertTrue(shown["errors"] and shown["warnings"] and shown["notes"], "the fixture has an error, a warning, and a note")
        lines = [("error", m) for m in shown["errors"]] + [("warning", m) for m in shown["warnings"]] + [("note", m) for m in shown["notes"]]
        self.assertEqual([(f["severity"], f["message"]) for f in shown["findings"]], lines)
        for f in shown["findings"]:
            self.assertEqual(json_schema.validate(f, URN + "finding"), [])
            self.assertTrue(f["code"].startswith("validate."))
            self.assertIn(f["next"], [r["next"] for r in findings.groups()["validate"]["codes"].values()])
        self.assertEqual(code, 1)

    def test_a_finding_names_the_file_only_when_the_message_opens_with_one(self):
        _, out, _ = run(self.root, "validate", "--json")
        by_message = {f["message"]: f for f in json.loads(out)["findings"]}
        named = by_message["specs/BAD.md: $: unknown field 'bogus'"]
        self.assertEqual(named["path"], "specs/BAD.md")
        for f in by_message.values():  # a path is a file that exists in the repository
            if "path" in f:
                self.assertTrue((self.root / f["path"]).is_file(), f)

    def test_a_message_gives_a_path_only_for_a_regular_file_inside_the_root(self):
        from aidd.workitems import finding_lists

        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            (root / "specs").mkdir(parents=True)
            (root / "specs" / "A.md").write_text("x", encoding="utf-8")
            (Path(d) / "outside.md").write_text("x", encoding="utf-8")
            (root / "link.md").symlink_to(Path(d) / "outside.md")
            cases = (
                ("a file in the repository", "specs/A.md: still contains TODO", "specs/A.md"),
                ("a file that is not there", "specs/B.md: still contains TODO", None),
                ("a folder", "specs: is a folder", None),
                ("a file above the root", "../outside.md: x", None),
                ("an absolute path", f"{Path(d) / 'outside.md'}: x", None),
                ("a link out of the root", "link.md: x", None),
                ("no colon", "specs/A.md still contains TODO", None),
                ("an empty message", "", None),
                ("a sentence that is no path", "no config: run `aidd init`", None),
            )
            for what, message, path in cases:
                with self.subTest(what):
                    found = finding_lists.validate_findings([], [message], [], root)
                    self.assertEqual(found[0].get("path"), path)

    def test_no_config_is_its_own_code(self):
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q")
            code, out, _ = run(Path(d), "validate", "--json")
        found = json.loads(out)["findings"]
        self.assertEqual((code, [f["code"] for f in found]), (1, ["validate.no_config"]))

    def test_a_clean_repository_gives_an_empty_list_not_a_missing_key(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d) / "repo", "team")
            _, out, _ = run(root, "validate", "--json")
        self.assertEqual(json.loads(out)["findings"], [])

    def test_doctor_gives_a_finding_for_each_check_that_failed_or_warned_and_none_for_the_rest(self):
        _, out, _ = run(self.root, "doctor", "--json")
        shown = json.loads(out)
        self.assertEqual(json_schema.validate(shown, "doctor.schema.json"), [])
        codes = {"fail": "doctor.check_failed", "warn": "doctor.check_warned"}
        expected = [(codes[c["result"]], c["message"]) for c in shown["checks"] if c["result"] in codes]
        self.assertEqual([(f["code"], f["message"]) for f in shown["findings"]], expected)
        self.assertTrue({c["result"] for c in shown["checks"]} > {"warn"}, "the fixture also has checks that are no finding")

    def test_status_gives_a_finding_for_a_config_that_does_not_load_and_the_exit_code_stays_1(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d) / "repo", "team")
            (root / ".aidd" / "config.yaml").write_text("profile: [unclosed\n", encoding="utf-8")
            code, out, err = run(root, "status", "--json")
        shown = json.loads(out)
        self.assertEqual(json_schema.validate(shown, "status.schema.json"), [])
        self.assertEqual((code, [f["code"] for f in shown["findings"]]), (1, ["config.unreadable"]))
        self.assertIn("does not load", err)
        self.assertIn("does not load", shown["findings"][0]["message"])

    def test_status_gives_a_finding_for_a_work_item_it_cannot_read_and_for_each_due_entry(self):
        from aidd.workitems import finding_lists

        answer = {
            "unreadable": [{"path": "specs/X.md", "error": "front matter is not YAML"}, {"path": "specs/Y.md", "error": "e", "place": "branch:b"}],
            "due": [{"path": "specs/Z.md", "what": "flag f is past its cleanup date", "next": {"what": "n"}}],
        }
        found = finding_lists.status_findings(answer)
        self.assertEqual(
            [(f["code"], f["path"], f["message"]) for f in found],
            [
                ("status.unreadable_item", "specs/X.md", "front matter is not YAML"),
                ("status.unreadable_item", "specs/Y.md", "e"),
                ("status.overdue", "specs/Z.md", "flag f is past its cleanup date"),
            ],
        )
        self.assertEqual(found[1]["data"], {"place": "branch:b"})
        self.assertEqual(finding_lists.status_findings({}), [])


class RegistryUseTests(Fixture):
    def test_a_code_the_registry_lacks_is_a_bug_that_raises(self):
        with self.assertRaises(KeyError):
            findings.finding("validate.nope", "m")

    def test_each_finding_takes_its_severity_and_next_step_from_its_row(self):
        for full, row in findings.codes().items():
            with self.subTest(full):
                made = findings.finding(full, "m", path="a.md", line=3, data={"k": "v"})
                self.assertEqual((made["severity"], made["next"]), (row["severity"], row["next"]))
                self.assertEqual(json_schema.validate(made, URN + "finding"), [])
                made["next"]["what"] = "changed"
                self.assertNotEqual(findings.codes()[full]["next"]["what"], "changed", "the row is never shared with a finding")


class ExplainCodeTests(Fixture):
    def test_every_code_of_the_registry_explains_with_its_title_why_and_next_step(self):
        listed = json.loads(run(self.root, "explain", "--list", "--json")[1])["words"]["finding_code"]
        self.assertEqual(listed, ["finding_code", *findings.codes()], "the word for the type, then every code in the registry's order")
        for full, row in findings.codes().items():
            with self.subTest(full):
                code, out, _ = run(self.root, "explain", full, "--json")
                match = [m for m in json.loads(out)["matches"] if m["type"] == "finding_code"]
                self.assertEqual(code, 0)
                self.assertEqual(len(match), 1)
                self.assertEqual((match[0]["name"], match[0]["what"], match[0]["source"]), (full, row["title"], "schemas/findings.json"))
                self.assertIn(row["why"], match[0]["why"])
                self.assertIn(row["next"]["what"], match[0]["why"])

    def test_a_code_in_another_case_or_with_dashes_is_the_same_code(self):
        for spelled in ("VALIDATE.ERROR", "validate.error"):
            self.assertEqual(run(self.root, "explain", spelled, "--json")[0], 0)

    def test_an_unknown_code_says_so_and_names_the_closest_only_when_one_is_close(self):
        cases = (("validate.erorr", "validate.error"), ("cli.invlid", "cli.invalid"), ("qqq.zzz", None))
        for typed, closest in cases:
            with self.subTest(typed):
                code, out, err = run(self.root, "explain", typed, "--json")
                shown = json.loads(out)
                self.assertEqual((code, shown["matches"], shown["error"]["code"]), (2, [], "cli.unknown_word"))
                self.assertIn("is not a word aidd knows", err)
                self.assertEqual(f"`{closest}`" in err, closest is not None, err)

    def test_the_word_for_the_type_is_answered(self):
        code, out, _ = run(self.root, "explain", "finding code", "--json")
        self.assertEqual((code, [m["type"] for m in json.loads(out)["matches"]]), (0, ["finding_code"]))


class McpParityTests(Fixture):
    def test_a_tool_returns_the_object_the_cli_prints(self):
        for tool, argv in (("validate", ["validate", "--json"]), ("status", ["status", "--json"])):
            with self.subTest(tool):
                _, out, _ = run(self.root, *argv)
                _, text = mcp_server.call(tool, {}, str(self.root))
                self.assertEqual(json.loads(text), json.loads(out))
        self.assertIn("findings", json.loads(mcp_server.call("validate", {}, str(self.root))[1]))

    def test_a_tool_error_is_the_error_object_the_cli_prints(self):
        _, out, _ = run(self.root, "risk", "--action", "pr.mrge", "--json")
        failed, text = mcp_server.call("risk", {"action": "pr.mrge"}, str(self.root))
        self.assertTrue(failed)
        self.assertEqual(json.loads(text), json.loads(out))

    def test_arguments_a_tool_cannot_use_are_refused_with_the_same_object(self):
        cases = (
            ("risk", {"paths": "a.py"}, "paths must be a list"),
            ("risk", {"paths": ["../x"]}, "is outside the repository"),
            ("risk", {}, "give one of paths, command, or action"),
            ("recall", {"words": 3}, "words must be a string"),
            ("record", {"type": "report", "by": "x/y", "data": "z"}, "data must be an object"),
            ("delegate_check", {"action": "pr.merge"}, "action and head are strings"),
        )
        for tool, args, said in cases:
            with self.subTest(tool=tool, args=args):
                failed, text = mcp_server.call(tool, args, str(self.root))
                shown = json.loads(text)
                self.assertEqual((failed, json_schema.validate(shown, URN + "error"), shown["error"]["code"]), (True, [], "cli.bad_arguments"))
                self.assertIn(said, shown["error"]["message"])

    def test_an_argument_the_tool_does_not_take_is_refused_with_the_closest_it_does(self):
        cases = (
            ("risk", {"path": ["a.py"]}, "`paths`"),
            ("risk", {"paths": ["a.py"], "chnage_type": "fix"}, "`change_type`"),
            ("status", {"all_branch": True}, "`all_branches`"),
            ("validate", {"zzzzz": 1}, None),
        )
        for tool, args, closest in cases:
            with self.subTest(tool=tool, args=args):
                failed, text = mcp_server.call(tool, args, str(self.root))
                message = json.loads(text)["error"]["message"]
                self.assertTrue(failed)
                self.assertIn("takes no argument", message)
                self.assertEqual(closest in message if closest else "Did you mean" not in message, True, message)
        failed, text = mcp_server.call("validate", {"paths": ["specs/BAD.md"]}, str(self.root))
        self.assertEqual((failed, "findings" in json.loads(text)), (True, True), "a tool's listed argument is taken")

    def test_every_tool_takes_the_arguments_its_schema_lists(self):
        """The check reads the tool list, so a tool's listed argument is never refused."""
        for tool in mcp_server.TOOLS:
            for argument in tool["inputSchema"]["properties"]:
                with self.subTest(tool=tool["name"], argument=argument):
                    self.assertIsNone(mcp_server._unknown_argument(tool["name"], {argument: 1}))


if __name__ == "__main__":
    unittest.main()
