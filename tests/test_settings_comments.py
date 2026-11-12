"""A settings file a person keeps takes aidd's ask rules without losing anything of theirs.

The invariant: for a harness whose documentation says its settings file takes comments (VS Code's `.vscode/settings.json`,
OpenCode's `opencode.jsonc`, Qwen Code's `.qwen/settings.json`), aidd reads the file with them and writes into the file the
person keeps, keeping every comment, the order and value of every other setting, the indentation, the line endings, and a byte
order mark. It writes the same ask rules it writes into an empty folder. It never writes a file it cannot read back, and a
file it cannot edit safely it leaves as it is and says what to do. A harness whose file is strict JSON still refuses a comment.
"""

import contextlib
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers
from helpers import git

from aidd import config, risk
from aidd.config import harness_settings
from aidd.risk import jsonc

PATTERNS = risk.harness_patterns(risk.rule_set(None), "main")
BOM = "\ufeff"
COMMENT = re.compile(r"//[^\r\n]*|/\*.*?\*/", re.S)
LEDGER = Path(config.HARNESS_RULES_FILE)

VSCODE = {
    "comments and trailing commas": (
        '// Editor settings\n{\n  // keep tabs narrow\n  "editor.tabSize": 2, // two\n  "chat.tools.terminal.autoApprove": {\n    "npm test": true, // mine\n  },\n'
        '  "files.eol": "\\n",\n  /* the end */\n}\n'
    ),
    "no approval table yet": '// my settings\n{\n  "editor.tabSize": 2, // two\n  "files.eol": "\\n" // last\n}\n',
    "tabs": '{\n\t// c\n\t"editor.tabSize": 2,\n\t"files.eol": "\\n"\n}\n',
    "one line": '{"editor.tabSize": 2}',
    "own entries, one false": '{\n  "chat.tools.terminal.autoApprove": {\n    "rm -rf": false, // careful\n    "ls": true\n  }\n}\n',
    "empty": "",
    "only whitespace": "\n\n",
    "only a comment": "// my settings, none yet\n",
}
# The same shapes with Windows line endings and a byte order mark, as an editor on Windows saves them.
VSCODE["comments and trailing commas, CRLF and BOM"] = BOM + VSCODE["comments and trailing commas"].replace("\n", "\r\n")
VSCODE["tabs, CRLF"] = VSCODE["tabs"].replace("\n", "\r\n")
# After aidd's rules come out again, the text is the original, byte for byte (the approval table was there before).
EXACT = ("comments and trailing commas", "comments and trailing commas, CRLF and BOM", "own entries, one false")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))  # exact bytes: write_text would turn a line ending into the platform's


def read(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def clean_entries(fmt: str) -> list[str]:
    """What aidd records for `fmt` when it writes into an empty folder."""
    with tempfile.TemporaryDirectory() as d:
        risk.apply_harness_rules(Path(d), fmt, PATTERNS)
        return sorted(json.loads((Path(d) / LEDGER).read_text(encoding="utf-8"))[fmt])


class InPlace(unittest.TestCase):
    def root(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def check_in_place(self, fmt: str, rel: str, text: str, syntax: str, exact: bool = False) -> None:
        root = self.root()
        write(root / rel, text)
        theirs = jsonc.loads(text, syntax)
        assert isinstance(theirs, dict)
        done = risk.apply_harness_rules(root, fmt, PATTERNS)
        self.assertTrue([d for d in done if "ask rules into" in d], done)
        new = read(root / rel)
        data = jsonc.loads(new, syntax)  # it reads back as the harness reads it
        assert isinstance(data, dict)
        self.assertEqual(sorted(json.loads(read(root / LEDGER))[fmt]), clean_entries(fmt), "the same rules an empty folder gets")
        for comment in COMMENT.findall(text):
            self.assertIn(comment, new, "a comment of theirs stays")
        for key, value in theirs.items():
            if not isinstance(value, dict):
                self.assertEqual(data[key], value, key)
        self.assertEqual([k for k in data if k in theirs], list(theirs), "their keys keep their order")
        self.assertEqual(new.startswith(BOM), text.startswith(BOM))
        if "\r\n" in text:
            self.assertIsNone(re.search(r"(?<!\r)\n", new), "every line ending stays CRLF")
        if text.startswith("\t", text.find("\n") + 1) or "\n\t" in text:
            self.assertNotRegex(new, r"\n {2}\S", "their tabs stay the indentation")
        again = risk.apply_harness_rules(root, fmt, PATTERNS)
        self.assertEqual((again, read(root / rel)), ([], new), "a second run changes nothing")
        risk.remove_harness_rules(root)
        left = read(root / rel) if (root / rel).exists() else ""
        for comment in COMMENT.findall(text):
            self.assertIn(comment, left, "a comment of theirs stays when aidd's rules go")
        if exact:
            self.assertEqual(left, text, "aidd's rules came out, and nothing else moved")
        else:
            gone = jsonc.loads(left, syntax) if left.strip() else {}
            assert isinstance(gone, dict)
            self.assertEqual({k: v for k, v in gone.items() if v != {}}, {k: v for k, v in theirs.items() if v != {}})

    def test_vscode_keeps_everything_a_person_wrote(self):
        for name, text in VSCODE.items():
            with self.subTest(shape=name):
                self.check_in_place("vscode", ".vscode/settings.json", text, "jsonc", exact=name in EXACT)

    def test_a_file_that_is_no_object_or_does_not_parse_is_left_alone_with_the_next_step(self):
        cases = {
            "an array": "[]",
            "a string": '"x"',
            "a number": "3",
            "a missing brace": '{\n  "editor.tabSize": 2\n',
            "a table that is no object": '{"chat.tools.terminal.autoApprove": []}',
            "a comment that never closes": "{ /* ",
            "a key twice": '{"chat.tools.terminal.autoApprove": {"a": true}, "chat.tools.terminal.autoApprove": {"b": true}}',
        }
        for name, text in cases.items():
            with self.subTest(shape=name):
                root = self.root()
                write(root / ".vscode/settings.json", text)
                with self.assertRaises(ValueError) as caught:
                    risk.apply_harness_rules(root, "vscode", PATTERNS)
                self.assertRegex(str(caught.exception), r"fix it|by hand")
                self.assertEqual(read(root / ".vscode/settings.json"), text)
                self.assertFalse((root / LEDGER).exists(), "nothing recorded for a file aidd did not write")

    def test_opencode_writes_into_the_jsonc_file_a_person_keeps(self):
        text = (
            '{\n  // my OpenCode settings\n  "permission": {"bash": "allow"},\n  "permissions": [\n    {"action": "shell", "resource": "*", "effect": "allow"}, // default\n'
            '  ],\n  "theme": "dark", // look\n}\n'
        )
        root = self.root()
        write(root / "opencode.jsonc", text)
        risk.apply_harness_rules(root, "opencode", PATTERNS)
        self.assertFalse((root / "opencode.json").exists(), "no second file beside the person's")
        new = read(root / "opencode.jsonc")
        data = jsonc.loads(new, "jsonc")
        assert isinstance(data, dict)
        self.assertEqual((data["theme"], data["permission"]), ("dark", {"bash": "allow"}))
        self.assertEqual(data["permissions"][0], {"action": "shell", "resource": "*", "effect": "allow"}, "their default stays first")
        self.assertEqual(len([r for r in data["permissions"] if r["effect"] == "ask"]), len(clean_entries("opencode")))
        for comment in ("// my OpenCode settings", "// default", "// look"):
            self.assertIn(comment, new)
        self.assertEqual(risk.apply_harness_rules(root, "opencode", PATTERNS), [])
        risk.remove_harness_rules(root)
        self.assertEqual(read(root / "opencode.jsonc"), text)

    def test_opencode_with_both_names_writes_the_first_and_says_what_it_does_not_know(self):
        root = self.root()
        write(root / "opencode.json", "{}")
        write(root / "opencode.jsonc", "// theirs\n{}\n")
        risk.apply_harness_rules(root, "opencode", PATTERNS)
        self.assertEqual(read(root / "opencode.jsonc"), "// theirs\n{}\n")
        self.assertTrue(json.loads(read(root / "opencode.json"))["permissions"])
        notes = risk.opencode_shadow_warnings(root, PATTERNS)
        self.assertEqual(len([n for n in notes if "are both here" in n and "do not say which wins" in n]), 1, notes)

    def test_qwen_code_takes_comments_but_no_trailing_comma(self):
        root = self.root()
        text = '{\n  // my model\n  "model": "x", // pinned\n  "permissions": {\n    "deny": ["Bash(rm -rf /)"] // never\n  }\n}\n'
        self.check_in_place("qwen", ".qwen/settings.json", text, "comments", exact=True)
        write(root / ".qwen/settings.json", '{\n  "model": "x",\n}\n')
        with self.assertRaises(ValueError) as caught:
            risk.apply_harness_rules(root, "qwen", PATTERNS)
        self.assertIn("fix it", str(caught.exception))

    def test_claude_code_stays_strict_json(self):
        root = self.root()
        text = '// a comment\n{\n  "model": "x"\n}\n'
        write(root / ".claude/settings.json", text)
        with self.assertRaises(ValueError) as caught:
            risk.apply_harness_rules(root, "claude-code", PATTERNS)
        self.assertIn("fix it", str(caught.exception))
        self.assertEqual(read(root / ".claude/settings.json"), text)

    def test_every_write_reads_back_as_the_new_settings_or_is_refused(self):
        """The guard under every edit: a patch that does not read back as exactly the new data raises, never writes."""
        old = {"a": {"b": 1}, "list": [1, 2, 3]}
        text = '{\n  "a": {"b": 1},\n  "list": [1, 2, 3] // c\n}\n'
        for new in ({"a": {"b": 2}, "list": [1, 2, 3]}, {"a": {"b": 1}, "list": [3]}, {"x": {"y": [1]}}, {}, {"a": {"b": 1}, "list": [1, 2, 3], "z": 1}):
            with self.subTest(new=new):
                out = jsonc.patch(text, old, new, "jsonc")
                self.assertEqual(jsonc.loads(out), new)
                if "list" in new and new["list"] == [1, 2, 3]:
                    self.assertIn("// c", out)
        with mock.patch.object(jsonc, "_edit", return_value="{}"):
            with self.assertRaises(ValueError):
                jsonc.patch(text, old, {"a": 1}, "jsonc")


class AsAPersonRunsIt(unittest.TestCase):
    """`aidd init`, then `aidd upgrade`, then `aidd doctor`, on a repository whose settings file holds the person's own
    comments, and the file read back after each step."""

    def run_steps(self, key: str, rel: str, text: str, syntax: str) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        git(root, "init", "-q", "-b", "main")
        write(root / rel, text)
        label = config.HARNESSES[key].label
        with (
            contextlib.chdir(root),
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(harness_settings, "user_plugins_enabled", return_value=set()),
        ):
            code, said = helpers.run_cli("init", "--harness", key, "--ci", "none")
            self.assertEqual(code, 0, said)
            self.assertRegex(said, rf"wrote\s+ask rules into {re.escape(rel)}: added \d+")
            after_init = read(root / rel)
            self.assertEqual(jsonc.loads(after_init, syntax) is not None, True)
            for comment in COMMENT.findall(text):
                self.assertIn(comment, after_init)
            code, said = helpers.run_cli("upgrade")
            self.assertNotIn("ask rules into", said, "init left the rules current")
            cfg = root / ".aidd" / "config.yaml"
            cfg.write_text(cfg.read_text(encoding="utf-8") + "risks:\n  rules:\n    - {action: git.tag.create, level: allow}\n", encoding="utf-8")
            code, dry = helpers.run_cli("upgrade")
            self.assertRegex(dry, rf"would write ask rules into {re.escape(rel)}: removed \d+ \(`git.tag.create` \d+\)")
            self.assertEqual(read(root / rel), after_init, "a dry run writes nothing")
            code, said = helpers.run_cli("upgrade", "--yes")
            self.assertRegex(said, rf"wrote\s+ask rules into {re.escape(rel)}: removed")
            for comment in COMMENT.findall(text):
                self.assertIn(comment, read(root / rel))
            code, report = helpers.run_cli("doctor")
            self.assertIn(f"{label}: its ask rules match the risk rules", report)
            self.assertNotIn("kept", "\n".join(line for line in report.splitlines() if label in line and "settings" in line))

    def test_vscode(self):
        self.run_steps("copilot", ".vscode/settings.json", VSCODE["comments and trailing commas"], "jsonc")

    def test_opencode_jsonc(self):
        text = '{\n  // mine\n  "theme": "dark", // look\n  "permissions": [\n  ],\n}\n'
        self.run_steps("opencode", "opencode.jsonc", text, "jsonc")

    def test_qwen_code(self):
        self.run_steps("qwen-code", ".qwen/settings.json", '{\n  // mine\n  "model": "x" // pinned\n}\n', "comments")


if __name__ == "__main__":
    unittest.main()
