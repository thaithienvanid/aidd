"""A tool's refusal names the tool's arguments, never the command line's flags.

An agent that calls a tool sees its input schema and no `--flag`. So an error that a tool returns says `change_type`, where the
command says `--change-type`, and it never sends the agent to a flag it cannot give. A command in backticks stays a command.

- every bad call below ends in the error object, and its words hold no flag outside backticks;
- the words name the argument that was wrong;
- every argument a tool lists with a fixed set of values is refused, in the argument's own name, when it holds another one."""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from helpers import git, make_repo

from aidd.cli import mcp_server

FLAG = re.compile(r"(?<![\w-])--[a-z]")

# (the tool, the arguments of the call, the argument the words must name)
CALLS = (
    ("risk", {"paths": ["a.py"], "area": "payments"}, "area"),
    ("risk", {"paths": ["a.py"], "branch": "default"}, "branch"),
    ("risk", {"paths": ["a.py"], "route": "normal"}, "route"),
    ("risk", {"paths": ["a.py"], "role": "developer"}, "role"),
    ("risk", {"paths": ["a.py"], "folder": "x"}, "folder"),
    ("risk", {"command": "ls", "change_type": "fix"}, "change_type"),
    ("risk", {"command": "ls", "dimensions": ["security"]}, "dimensions"),
    ("risk", {"command": "ls", "irreversible": True}, "irreversible"),
    ("risk", {"action": "pr.merge", "change_type": "fix"}, "change_type"),
    ("risk", {"action": "pr.mrge"}, "action"),
    ("risk", {"action": "pr.merge", "branch": "nowhere"}, "branch"),
    ("risk", {"action": "pr.merge", "route": "nowhere"}, "route"),
    ("risk", {"paths": ["a.py"], "change_type": "nowhere"}, "change_type"),
    ("risk", {"paths": ["a.py"], "dimensions": ["nowhere"]}, "dimensions"),
    ("recall", {"words": "x", "limit": 0}, "limit"),
    ("recall", {"words": "x", "limit": 9999}, "limit"),
    ("recall", {"words": "  "}, "words"),
    ("record", {"type": "nope", "by": "x/y", "data": {}}, "type"),
    ("record", {"type": "report", "by": "", "data": {}}, "by"),
    ("record", {"type": "report", "data": {}}, "by"),
    ("record", {"by": "x/y", "data": {}}, "type"),
    ("record", {"type": "report", "by": "x/y", "data": {}, "subject": 3}, "subject"),
    ("delegate_check", {"action": "x", "head": "abc"}, "head"),
    ("delegate_packet", {"action": "pr.merge", "head": "short"}, "head"),
)


class ArgumentWordsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.root = str(make_repo(Path(tmp.name) / "repo", "team", spec="specs/SPEC-220.md"))
        cls.head = git(Path(cls.root), "rev-parse", "HEAD")

    def error(self, tool: str, args: dict) -> dict:
        """The error object a client reads for one `tools/call`, as the server answers it."""
        answer = mcp_server._tools_call({"name": tool, "arguments": args}, self.root)
        self.assertTrue(answer["isError"], f"{tool} {args} was answered")
        return json.loads(answer["content"][0]["text"])["error"]

    def test_a_refusal_holds_no_flag_outside_backticks_and_names_the_argument(self):
        for tool, args, argument in CALLS:
            with self.subTest(tool=tool, args=args):
                error = self.error(tool, args)
                outside = "`".join(part for i, part in enumerate((error["message"] + "`" + error["next"]["what"]).split("`")) if i % 2 == 0)
                self.assertIsNone(FLAG.search(outside), error["message"])
                self.assertIn(argument, error["message"])

    def test_every_listed_set_of_values_is_refused_in_the_arguments_name(self):
        base = {"risk": {"paths": ["a.py"]}, "record": {"by": "x/y", "data": {}}, "delegate_answer": {"action": "pr.merge", "head": self.head, "reason": "r"}}
        found = 0
        for tool in mcp_server.TOOLS:
            for argument, spec in tool["inputSchema"]["properties"].items():
                fixed = spec.get("enum") or spec.get("items", {}).get("enum")
                if not fixed:
                    continue
                found += 1
                value = "nowhere" if "enum" in spec else ["nowhere"]
                call = {**base.get(tool["name"], {}), argument: value}
                if tool["name"] == "risk" and argument in ("branch", "role", "route"):
                    call = {"action": "pr.merge", argument: value}
                with self.subTest(tool=tool["name"], argument=argument):
                    message = self.error(tool["name"], call)["message"]
                    self.assertIn(argument, message)
                    self.assertIsNone(FLAG.search("`".join(p for i, p in enumerate(message.split("`")) if i % 2 == 0)), message)
        self.assertGreaterEqual(found, 7, "the tools list their sets of values, and the check reads them from the list")

    def test_a_command_the_message_points_to_stays_a_command(self):
        error = self.error("risk", {"action": "pr.mrge"})
        self.assertIn("`aidd risk --list`", error["message"])


if __name__ == "__main__":
    unittest.main()
