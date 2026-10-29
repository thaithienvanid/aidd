"""A person records a proposal's go/no-go and sign-off with one command, never by hand-editing YAML (UX audit U9), and
`aidd digest` needs no `--since` (U5)."""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import git, make_repo, run_cli

from aidd import tracking, workitems
from aidd.cli import app, arguments
from aidd.guard import command_check
from aidd.platforms import local_land


class _Terminal(io.StringIO):
    """A stream that says it is a terminal, as a person's shell is."""

    def isatty(self):
        return True


FRONT = '---\naidd_version: "1.0.0"\nkind: proposal\nid: "PROP-1"\n# go_no_go: {decision: go, by: "@lead"}\nexclusions: []\n---\n\n# Body\n'


class RecordDecisionTests(unittest.TestCase):
    def test_it_takes_the_placeholders_place_and_keeps_the_rest(self):
        new = workitems.record_decision(FRONT, "go_no_go", {"decision": "go", "by": "@ana", "decided_on": "2026-10-16"})
        self.assertIn('go_no_go: {decision: go, by: "@ana", decided_on: "2026-10-16"}\n', new)
        self.assertNotIn("# go_no_go", new)
        self.assertTrue(new.endswith("---\n\n# Body\n"))
        self.assertIn("exclusions: []", new)

    def test_it_replaces_a_line_or_a_block_and_appends_when_absent(self):
        once = workitems.record_decision(FRONT, "go_no_go", {"decision": "go", "by": "@ana", "decided_on": "2026-10-16"})
        twice = workitems.record_decision(once, "go_no_go", {"decision": "no_go", "by": "@ana", "decided_on": "2026-10-17"})
        self.assertEqual(twice.count("go_no_go:"), 1)
        self.assertIn("decision: no_go", twice)
        block = FRONT.replace("exclusions: []\n", 'sign_off:\n  by: "@x"\n  decided_on: "2026-01-01"\nexclusions: []\n')
        signed = workitems.record_decision(block, "sign_off", {"by": "@ana", "decided_on": "2026-10-16", "hash": "0" * 32})
        self.assertNotIn('by: "@x"', signed)
        self.assertIn("exclusions: []", signed)
        added = workitems.record_decision(FRONT, "sign_off", {"by": "@ana", "decided_on": "2026-10-16", "hash": "0" * 32})
        self.assertIn('sign_off: {by: "@ana"', added.split("\n---\n", 1)[0])

    def test_only_the_two_decisions(self):
        with self.assertRaises(ValueError):
            workitems.record_decision(FRONT, "outcome", {"decision": "won"})


class CommandTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_repo(Path(tmp.name).resolve() / "repo", "team")
        with contextlib.chdir(self.root):
            code, out = run_cli("new", "proposal", "PROP-1", "--title", "Move billing to the cloud", "--audience", "internal", "--addressee", "the board")
        self.assertEqual(code, 0, out)
        self.path = self.root / "proposals" / "PROP-1" / "proposal.md"

    def run_as_person(self, *argv: str, answer: str = "y") -> tuple[int, str]:
        """`aidd proposal <argv>` in-process, as a person at an interactive terminal who answers `answer`."""
        out = _Terminal()
        person = {k: v for k, v in os.environ.items() if k not in local_land.AGENT_ENV}
        with (
            contextlib.chdir(self.root),
            mock.patch.dict(os.environ, person, clear=True),
            mock.patch.object(sys, "stdin", _Terminal()),
            mock.patch("builtins.input", return_value=answer) as asked,
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(out),
        ):
            code = app.main(["proposal", *argv])
        self.asked = asked
        return code, out.getvalue()

    def test_decide_then_sign_off_by_id(self):
        code, out = self.run_as_person("decide", "PROP-1", "go", "--reason", "fits our strategy", "--by", "@ana")
        self.assertEqual(code, 0, out)
        self.asked.assert_called_once_with("Record go on PROP-1 as @ana? [y/N] ")
        data = workitems.load_proposal(self.path)
        self.assertEqual(data["go_no_go"], {"decision": "go", "by": "@ana", "decided_on": dt.date.today().isoformat(), "reason": "fits our strategy"})
        self.assertEqual(workitems.proposal_status(data), "drafting")
        code, out = self.run_as_person("sign-off", "PROP-1", "--by", "@ana")
        self.assertEqual(code, 0, out)
        data = workitems.load_proposal(self.path)
        self.assertEqual(data["sign_off"]["hash"], workitems.proposal_hash(self.path.read_text(encoding="utf-8")))
        self.assertEqual(workitems.proposal_status(data), "signed_off")
        self.assertIn("Commit it: git commit proposals/PROP-1/proposal.md", out)

    def test_sign_off_needs_a_go_and_no_answer_records_nothing(self):
        before = self.path.read_text(encoding="utf-8")
        code, out = self.run_as_person("sign-off", "PROP-1", "--by", "@ana")
        self.assertNotEqual(code, 0)
        self.assertIn("has no go yet", out)
        code, out = self.run_as_person("decide", "PROP-1", "no-go", "--by", "@ana", answer="")
        self.assertNotEqual(code, 0)
        self.assertIn("was not confirmed", out)
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

    def test_an_agent_shell_or_an_agent_account_cannot_decide(self):
        before = self.path.read_text(encoding="utf-8")
        with contextlib.chdir(self.root), mock.patch.dict(os.environ, {local_land.AGENT_ENV[0]: "1"}):
            code, out = run_cli("proposal", "decide", "PROP-1", "go", "--by", "@ana")
        self.assertNotEqual(code, 0)
        self.assertIn("a person's decision", out)
        code, out = self.run_as_person("decide", "PROP-1", "go", "--by", "agent:developer")
        self.assertNotEqual(code, 0)
        self.assertIn("agent account", out)
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

    def test_show_previews_and_a_dialog_records_exactly_what_it_showed(self):
        before = self.path.read_text(encoding="utf-8")
        with contextlib.chdir(self.root):
            code, out = run_cli("proposal", "decide", "PROP-1", "go", "--reason", "fits", "--show")
        self.assertEqual(code, 0, out)
        shown = json.loads(out)
        self.assertEqual((shown["decision"], shown["reason"], shown["problems"]), ("go", "fits", []))
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)  # --show records nothing
        with contextlib.chdir(self.root), arguments.mcp_dialog():
            code, out = run_cli("proposal", "decide", "PROP-1", "go", "--confirmed", "no-go", "--decided-via", "mcp:ide")
            self.assertEqual(code, 1, out)  # confirmed another decision than this records
            self.assertIn("you confirmed 'no-go'", out)
            code, out = run_cli("proposal", "decide", "PROP-1", "go", "--confirmed", "go", "--decided-via", "mcp:ide", "--by", "@else")
            self.assertEqual(code, 2, out)  # a dialog's answer is this machine's person, never one named
            code, out = run_cli("proposal", "decide", "PROP-1", "go", "--confirmed", "go", "--decided-via", "mcp:ide")
        self.assertEqual(code, 0, out)
        self.assertEqual(workitems.load_proposal(self.path)["go_no_go"]["decision"], "go")
        with contextlib.chdir(self.root):
            code, out = run_cli("proposal", "sign-off", "PROP-1", "--show")
        h = json.loads(out)["hash"]
        self.path.write_text(self.path.read_text(encoding="utf-8") + "\nThe price is now lower.\n", encoding="utf-8")
        with contextlib.chdir(self.root), arguments.mcp_dialog():
            code, out = run_cli("proposal", "sign-off", "PROP-1", "--confirmed", h, "--decided-via", "mcp:ide")
        self.assertEqual(code, 1, out)  # the text changed since the person saw it
        self.assertIn("the proposal changed since you saw it", out)
        self.assertNotIn("sign_off", workitems.load_proposal(self.path))
        # An `mcp:` confirmation counts only inside aidd's MCP server, never from a shell.
        with contextlib.chdir(self.root):
            code, out = run_cli("proposal", "decide", "PROP-1", "no-go", "--confirmed", "no-go", "--decided-via", "mcp:ide")
        self.assertNotEqual(code, 0)
        self.assertIn("counts only from aidd's MCP server", out)


class GuardTests(unittest.TestCase):
    def test_the_guard_denies_an_agent_a_proposal_decision(self):
        with tempfile.TemporaryDirectory() as d:
            root = str(make_repo(Path(d).resolve() / "repo", "team"))
            for cmd, denied in (
                ("aidd proposal decide PROP-1 go", True),
                ("uvx aidd proposal sign-off PROP-1 --by @ana", True),
                ("python3 -m aidd proposal decide proposals/PROP-1/proposal.md no-go", True),
                ("aidd proposal --by @ana decide PROP-1 go", True),  # an option before the action, as argparse allows
                ("aidd proposal --reason 'fits us' sign-off PROP-1", True),
                ("aidd proposal --by=@ana decide PROP-1 go", True),
                ('orca terminal send --terminal t1 --text "aidd proposal decide PROP-1 go" --enter', True),  # typed into a person's terminal
                ("tmux send-keys -t 0 'aidd proposal sign-off PROP-1' Enter", True),
                ("aidd proposal decide PROP-1 go --confirmed go", True),  # only a dialog's own process confirms
                ("aidd proposal decide PROP-1 go --show --confirmed go", True),
                ("aidd proposal decide PROP-1 go --show", False),  # a preview records nothing
                ("aidd proposal decide --help", False),
                ("aidd proposal matrix PROP-1", False),
                ("aidd proposal convert PROP-1", False),
            ):
                with self.subTest(cmd=cmd):
                    self.assertEqual(command_check.check_command(root, root, cmd, {})[0] == "deny", denied)


class DigestWindowTests(unittest.TestCase):
    def test_the_last_tag_else_the_last_week(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d).resolve() / "repo", "team", branch=None)
            today = dt.date(2026, 10, 16)
            self.assertEqual(tracking.default_since(root, today), "2026-10-09")
            git(root, "tag", "v1.2.0")
            self.assertEqual(tracking.default_since(root, today), "v1.2.0")
            with contextlib.chdir(root):
                code, out = run_cli("digest")
            self.assertEqual(code, 0, out)
            self.assertIn("since v1.2.0", out)


if __name__ == "__main__":
    unittest.main()
