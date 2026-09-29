"""Edit-time enforcement: the guard, the Claude Code hook, the MCP server, and their wiring."""

import io
import json
import shutil
import unittest

from helpers import ROOT, RepoTemplateCase, aidd_subprocess, git, make_repo

from aidd import guard, mcp, repo

SPEC = """+++
aidd_version = "1.0.0"
kind = "spec"
id = "S-1"
title = "Greeting"
owner_team = "core"
type = "feat"
route = "normal"
confidence = "high"
open_questions = []
trace_id = "s-1"
assisted_by = []
rollback = "Revert the PR."

[risk]
summary = "Adds a greeting."
dimensions = []
reversible = true

[[tasks]]
id = "S-1-T1"
title = "Implement"
scope = ["src/app/"]

[tests]
files = ["tests/test_app.py"]

[[tests.commands]]
name = "app"
command = ["python3", "tests/test_app.py"]
new_behavior = true
+++

## Context

Example.
"""


@unittest.skipUnless(shutil.which("git"), "git is required")
class AgentToolTests(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        make_repo(root, "solo", approvers=["@me"])
        (root / "specs" / "S-1.md").write_text(SPEC, encoding="utf-8")

    def test_guard_decisions(self):
        root = str(self.root)
        self.assertEqual(guard.check_edit(root, "src/app/x.py")[0], "allow")
        self.assertEqual(guard.check_edit(root, "specs/S-1.md")[0], "allow")
        # Before Spec approval the session writes the Spec's tests; once the Spec's status says Spec approval, nobody does.
        self.assertEqual(guard.check_edit(root, "tests/test_app.py")[0], "allow")
        self.assertEqual(guard.check_edit(root, "src/other/y.py")[0], "deny")
        spec = self.root / "specs" / "S-1.md"
        spec.write_text(spec.read_text(encoding="utf-8").replace('kind = "spec"', 'kind = "spec"\nstatus = "ready"', 1), encoding="utf-8")
        decision, reason = guard.check_edit(root, "tests/test_app.py")
        self.assertEqual(decision, "deny")
        self.assertIn("Spec approval again", reason)

    def test_without_a_spec_protected_paths_are_denied_with_a_route(self):
        (self.root / "specs" / "S-1.md").unlink()
        root = str(self.root)
        self.assertEqual(guard.check_edit(root, "src/anything.py")[0], "allow")
        decision, reason = guard.check_edit(root, ".github/workflows/ci.yml")
        self.assertEqual(decision, "deny")
        self.assertIn("major", reason)
        self.assertIn("get Spec approval", reason)

    def test_hook_speaks_the_claude_code_format(self):
        out = io.StringIO()
        event = {"tool_name": "Edit", "cwd": str(self.root), "tool_input": {"file_path": str(self.root / "src/other/y.py")}}
        guard.pre_edit_hook(io.StringIO(json.dumps(event)), out)
        decision = json.loads(out.getvalue())["hookSpecificOutput"]
        self.assertEqual((decision["hookEventName"], decision["permissionDecision"]), ("PreToolUse", "deny"))
        out = io.StringIO()
        event["tool_input"]["file_path"] = "src/app/x.py"
        guard.pre_edit_hook(io.StringIO(json.dumps(event)), out)
        self.assertEqual(out.getvalue(), "")

    def test_mcp_server_lists_and_calls_tools(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "check_edit", "arguments": {"path": "src/other/y.py"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "next", "arguments": {"paths": ["db/migrations/1.sql"]}}},
            {"jsonrpc": "2.0", "id": 5, "method": "nope"},
        ]
        out = io.StringIO()
        mcp.serve(io.StringIO("\n".join(json.dumps(m) for m in lines) + "\n"), out, root=str(self.root))
        replies = {r["id"]: r for r in map(json.loads, out.getvalue().splitlines())}
        self.assertEqual(sorted(replies), [1, 2, 3, 4, 5])
        self.assertEqual(replies[1]["result"]["serverInfo"]["name"], "aidd")
        self.assertIn("check_edit", [t["name"] for t in replies[2]["result"]["tools"]])
        self.assertTrue(replies[3]["result"]["content"][0]["text"].startswith("deny"))
        answer = json.loads(replies[4]["result"]["content"][0]["text"])
        self.assertEqual((answer["route"]["route"], answer["route"]["lane"], answer["route"]["pools"]), ("major", "spec", ["data"]))
        self.assertTrue(answer["route"]["reasons"])
        self.assertIsInstance(answer["next"], list)
        self.assertNotIn("assess", [t["name"] for t in replies[2]["result"]["tools"]])
        self.assertEqual(replies[5]["error"]["code"], -32601)

    def mcp_calls(self, *calls):
        """(isError, text) for each tools/call, sent through the stdio server as a client would."""
        lines = [{"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": n, "arguments": a}} for i, (n, a) in enumerate(calls, 1)]
        out = io.StringIO()
        mcp.serve(io.StringIO("".join(json.dumps(m) + "\n" for m in lines)), out, root=str(self.root))
        replies = {r["id"]: r["result"] for r in map(json.loads, out.getvalue().splitlines())}
        return [(replies[i]["isError"], replies[i]["content"][0]["text"]) for i in range(1, len(calls) + 1)]

    def test_mcp_validate_hash_change_and_gate_answer(self):
        (self.root / "src" / "app").mkdir(parents=True)
        (self.root / "src" / "app" / "x.py").write_text("GREETING = 'hi'\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "S-1\n\nAssisted-by: none")
        validate, hashed, change, gate = self.mcp_calls(
            ("validate", {"paths": ["specs/S-1.md"]}),
            ("hash", {"spec": "specs/S-1.md"}),
            ("change", {"type": "feat"}),
            ("gate", {"spec": "specs/S-1.md"}),
        )
        self.assertFalse(validate[0], validate[1])
        self.assertFalse(hashed[0], hashed[1])
        self.assertRegex(hashed[1], rf"^/aidd approve-spec S-1 [0-9a-f]{{32}} {git(self.root, 'rev-parse', 'HEAD')}$")
        self.assertFalse(change[0], change[1])
        self.assertIn("```toml aidd", change[1])
        self.assertFalse(gate[0], gate[1])  # fail and pending are answers, not tool errors
        self.assertIn("aidd gate:", gate[1])

    def test_mcp_refuses_paths_outside_the_repository(self):
        for name, args in (
            ("validate", {"paths": ["../x.md"]}),
            ("validate", {"paths": ["specs/../../x.md"]}),
            ("hash", {"spec": "../x.md"}),
            ("gate", {"spec": "/etc/passwd"}),
            ("gate", {"evidence": "../evidence.json"}),
            ("check_edit", {"path": ".."}),
        ):
            with self.subTest(name=name, args=args):
                is_error, text = self.mcp_calls((name, args))[0]
                self.assertTrue(is_error)
                self.assertIn("is outside the repository", text)
        # A name that merely starts with two dots is inside the repository.
        for p in ("..notes/x.md", "docs/..hidden.md", "specs/../specs/S-1.md"):
            self.assertTrue(mcp._is_safe_repo_path(p, str(self.root)), p)
        is_error, text = self.mcp_calls(("check_edit", {"path": "..notes/x.md"}))[0]
        self.assertFalse(is_error, text)
        self.assertNotIn("outside the repository", text)

    def test_the_hook_command_denies_through_the_real_entry_point(self):
        event = {"tool_name": "Edit", "cwd": str(self.root), "tool_input": {"file_path": str(self.root / "src/other/y.py")}}
        run = aidd_subprocess("hook", "pre-edit", cwd=self.root, input=json.dumps(event))
        self.assertEqual(run.returncode, 0, run.stderr)
        decision = json.loads(run.stdout)["hookSpecificOutput"]
        self.assertEqual((decision["hookEventName"], decision["permissionDecision"]), ("PreToolUse", "deny"))
        self.assertTrue(decision["permissionDecisionReason"].startswith("aidd: "))
        event["tool_input"]["file_path"] = str(self.root / "src/app/x.py")
        allowed = aidd_subprocess("hook", "pre-edit", cwd=self.root, input=json.dumps(event))
        self.assertEqual((allowed.returncode, allowed.stdout), (0, ""))

    def test_init_wires_hooks_without_clobbering(self):
        settings = self.root / ".claude" / "settings.json"
        settings.parent.mkdir(exist_ok=True)
        settings.write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]}}), encoding="utf-8")
        repo.init(self.root, profile="solo", ci="none", links=[], skill=False, agent_hooks=True)
        repo.init(self.root, profile="solo", ci="none", links=[], skill=False, agent_hooks=True)
        data = json.loads(settings.read_text(encoding="utf-8"))
        self.assertEqual(data["permissions"], {"allow": ["Bash(ls)"]})
        self.assertEqual(len(data["hooks"]["PreToolUse"]), 1)
        self.assertEqual(json.loads((self.root / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["aidd"], repo.mcp_server())
        self.assertEqual(repo.mcp_server()["args"][-1], "mcp")


class PluginWiringTests(unittest.TestCase):
    def test_plugin_ships_the_server_and_the_hook(self):
        plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(plugin["mcpServers"]["aidd"]["args"], ["-m", "aidd", "mcp"])
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        self.assertIn("aidd hook pre-edit", hooks["hooks"]["PreToolUse"][0]["hooks"][0]["command"])


if __name__ == "__main__":
    unittest.main()
