"""Grok Build: native role files, flow skills, and aidd's guard hook in Grok's own event shape.

Grok sends hookEventName pre_tool_use, toolName, toolInput, and subagentType, and it reads a top-level systemMessage
from SessionStart. The guard's checks stay on Claude Code's vocabulary; a Dialect translates. The protocol is Grok
Build's hooks guide (grok 1.0.60 ships a copy): a Stop event says `stopHookActive`, a prompt hook's context is dropped,
an `allow` approves nothing, and a skill is a slash command only with `user-invocable: true`.
"""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import git, make_repo
from test_session_hooks import SPEC

from aidd import config
from aidd.docsgen.counts import harnesses_summary
from aidd.guard import approval_commands, dialects, pre_tool, session_hooks
from aidd.knowledge import agent_models
from aidd.setup import adoption, doctor_checks, harness_text, team_install, uninstalling

READ_ONLY = frozenset({"reviewer", "verifier", "domain-expert"})
READ_TOOLS = frozenset({"read_file", "grep", "list_dir", "run_terminal_command", "web_search", "web_fetch"})
WRITE_TOOLS = frozenset({"search_replace", "write"})
HOOK_EVENTS = ("PreToolUse", "SessionStart", "UserPromptSubmit", "Stop", "SubagentStop", "PreCompact")


def tool_set(text: str) -> set[str]:
    """The tools named on the one `tools:` line of a Grok agent file."""
    for line in text.splitlines():
        if line.startswith("tools:"):
            return {part.strip() for part in line.split(":", 1)[1].split(",") if part.strip()}
    raise AssertionError("no tools line")


def grok_event(root: Path, tool: str, tool_input: dict, **extra) -> dict:
    """One Grok PreToolUse event. It sets Grok's names only, never tool_name, tool_input, or agent_type."""
    return {
        "hookEventName": "pre_tool_use",
        "toolName": tool,
        "toolInput": tool_input,
        "cwd": str(root),
        "workspaceRoot": str(root),
        **extra,
    }


def guard_stdout(root: Path, tool: str, tool_input: dict, **extra) -> str:
    """What the guard writes for one Grok tool call. Empty when it has no opinion."""
    out = io.StringIO()
    code = pre_tool.pre_tool_hook(io.StringIO(json.dumps(grok_event(root, tool, tool_input, **extra))), out)
    if code != 0:
        raise AssertionError(code)
    return out.getvalue()


def permission(body: str) -> str:
    """The permissionDecision of a deny, or a failure when the guard wrote nothing."""
    if not body:
        raise AssertionError("expected a deny, got empty stdout")
    return json.loads(body)["hookSpecificOutput"]["permissionDecision"]


class NativeFilesTests(unittest.TestCase):
    def test_grok_is_native_and_the_docs_name_its_hooks(self):
        self.assertIn("grok-build", team_install.NATIVE_AGENT_HARNESSES)
        self.assertIn("grok-build", harness_text.VOICES)
        harness = config.HARNESSES["grok-build"]
        self.assertIn(".grok/agents", harness.agent_dirs)
        self.assertIn(".grok/agents", harness.wiring)
        self.assertIn(".grok/hooks/aidd.json", harness.wiring)
        self.assertIn("aidd mcp", harness.you)
        summary = harnesses_summary()
        self.assertIn("| **Grok Build** |", summary)  # a row of its own, as an agent the guard runs in
        self.assertIn(".grok/hooks", summary)
        section = team_install.team_section(["grok-build"])
        self.assertIn("advisory", section)
        self.assertIn(".grok/hooks/aidd.json", section)
        self.assertIn("subagentType", section)

    def test_role_files_grant_grok_tools_and_no_spawn(self):
        files = team_install.team_files(["grok-build"], claude_files=False)
        agents = {rel: text for rel, text in files.items() if rel.startswith(".grok/agents/")}
        self.assertGreaterEqual(len(agents), 17)
        for rel, text in agents.items():
            tools = tool_set(text)
            role = Path(rel).stem.removeprefix("aidd-")
            with self.subTest(role=role):
                self.assertTrue(READ_TOOLS <= tools, tools)
                self.assertNotIn("spawn_subagent", tools)
                if role in READ_ONLY:
                    self.assertTrue(tools.isdisjoint(WRITE_TOOLS), tools)
                else:
                    self.assertTrue(WRITE_TOOLS <= tools, tools)

    def test_the_implement_skill_spawns_without_a_worktree_flag(self):
        files = team_install.team_files(["grok-build"], claude_files=False)
        skill = files[".grok/skills/aidd-implement/SKILL.md"]
        self.assertIn("spawn_subagent", skill)
        self.assertNotIn("isolation:", skill)


class DialectTests(unittest.TestCase):
    def grok(self, event: dict) -> dict:
        dialect = dialects.of(event)
        self.assertEqual(dialect.key, "grok-build")
        self.assertFalse(dialect.names_its_session)
        return dialect.normalize(event)

    def test_shell_edit_and_write_map_onto_the_guard(self):
        root = "/tmp/repo"
        shell = self.grok(
            {
                "hookEventName": "pre_tool_use",
                "toolName": "run_terminal_command",
                "toolInput": {"command": "git status"},
                "subagentType": "aidd-reviewer",
                "sessionId": "sess-1",
                "workspaceRoot": root,
            }
        )
        self.assertEqual(shell["agent_type"], "aidd-reviewer")
        self.assertEqual(shell["tool_name"], "Bash")
        self.assertEqual(shell["tool_input"], {"command": "git status"})
        self.assertEqual(shell["session_id"], "sess-1")
        self.assertEqual(shell["cwd"], root)
        edit = self.grok(
            {
                "hookEventName": "pre_tool_use",
                "toolName": "search_replace",
                "toolInput": {"file_path": "src/app.py", "old_string": "a", "new_string": "b", "replace_all": True},
                "workspaceRoot": root,
            }
        )
        self.assertEqual(edit["tool_name"], "Edit")
        self.assertEqual(edit["tool_input"], {"file_path": "src/app.py", "old_string": "a", "new_string": "b", "replace_all": True})
        write = self.grok(
            {
                "hookEventName": "pre_tool_use",
                "toolName": "write",
                "toolInput": {"file_path": "src/app.py", "content": "print(1)\n"},
                "workspaceRoot": root,
            }
        )
        self.assertEqual(write["tool_name"], "Write")
        self.assertEqual(write["tool_input"], {"file_path": "src/app.py", "content": "print(1)\n"})

    def test_a_server_tool_and_use_tool_become_mcp_calls(self):
        direct = self.grok({"hookEventName": "pre_tool_use", "toolName": "aidd__gate", "toolInput": {"paths": ["src/a.py"]}, "workspaceRoot": "/tmp/repo"})
        self.assertEqual(direct["tool_name"], "mcp__aidd__gate")
        self.assertEqual(direct["tool_input"], {"paths": ["src/a.py"]})
        wrapped = self.grok(
            {
                "hookEventName": "pre_tool_use",
                "toolName": "use_tool",
                "toolInput": {"tool_name": "aidd__gate", "tool_input": {"spec": "specs/SPEC-1.md"}},
                "workspaceRoot": "/tmp/repo",
            }
        )
        self.assertEqual(wrapped["tool_name"], "mcp__aidd__gate")
        self.assertEqual(wrapped["tool_input"], {"spec": "specs/SPEC-1.md"})

    def test_claude_and_antigravity_keep_their_dialects(self):
        claude = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": "/tmp/repo"}
        self.assertEqual(dialects.of(claude).key, "claude-code")
        write = {"tool_name": "Write", "tool_input": {"file_path": "x.md", "content": "hi"}, "cwd": "/tmp/repo"}
        self.assertEqual(dialects.of(write).key, "claude-code")
        agy = {"conversationId": "c", "workspacePaths": ["/tmp/repo"], "toolCall": {"name": "run_command", "args": {"CommandLine": "ls"}}}
        self.assertEqual(dialects.of(agy).key, "antigravity")


class GuardTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        # An active normal Spec: the developer may write tests only on the fast lane, after the Spec is gone
        # (tests/test_team.py). The spec-lane deny needs an active Spec, so this repository keeps SPEC-220.
        self.root = make_repo(
            Path(tmp.name).resolve() / "repo",
            "solo",
            approvers=["email:me@example.com"],
            spec="02-normal-feature:specs/SPEC-220.md",
        )

    def test_a_reviewer_edit_a_developer_test_write_and_a_merge_are_denied(self):
        reviewer = guard_stdout(self.root, "search_replace", {"file_path": "src/app.py", "old_string": "a", "new_string": "b"}, subagentType="aidd-reviewer")
        self.assertEqual(permission(reviewer), "deny")
        developer = guard_stdout(self.root, "write", {"file_path": "tests/foo.py", "content": "x\n"}, subagentType="aidd-developer")
        self.assertEqual(permission(developer), "deny")
        merge = guard_stdout(self.root, "run_terminal_command", {"command": "gh pr merge 1"})
        self.assertEqual(permission(merge), "deny")

    def test_a_harmless_command_is_no_opinion(self):
        self.assertEqual(guard_stdout(self.root, "run_terminal_command", {"command": "python3 -m unittest"}), "")

    def test_a_broken_guard_denies_with_permission_decision_when_required(self):
        event = json.dumps(grok_event(self.root, "run_terminal_command", {"command": "ls"}))
        boom = mock.Mock(side_effect=RuntimeError("boom"))
        patches = [mock.patch.object(dialects.Dialect, "normalize", boom)]
        grok = getattr(dialects, "Grok", None)
        if grok is not None:
            patches.append(mock.patch.object(grok, "normalize", boom))
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            out = io.StringIO()
            pre_tool.pre_tool_hook(io.StringIO(event), out)
            self.assertEqual(out.getvalue(), "")
            with mock.patch.dict(os.environ, {approval_commands.FAIL_CLOSED_ENV: "1"}):
                out = io.StringIO()
                pre_tool.pre_tool_hook(io.StringIO(event), out)
                self.assertEqual(json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecision"], "deny")


class HookFileTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        git(self.root, "init", "-q")

    def init(self) -> list[str]:
        chosen = adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=["grok-build"], approvers=["email:me@example.com"], team=True)
        return adoption.init(self.root, chosen)

    def test_init_writes_the_hook_doctor_names_it_and_uninstall_removes_it(self):
        self.init()
        path = self.root / ".grok" / "hooks" / "aidd.json"
        agent = self.root / ".grok" / "agents" / "aidd-developer.md"
        skill = self.root / ".grok" / "skills" / "aidd-implement" / "SKILL.md"
        self.assertTrue(path.is_file(), "hook file missing")
        from aidd.setup import grok_wiring

        data = json.loads(path.read_text(encoding="utf-8"))
        pre = data["hooks"]["PreToolUse"][0]
        self.assertEqual(pre["matcher"], "*")
        self.assertEqual(pre["hooks"][0]["command"], grok_wiring.hook_command("pre-tool"))
        self.assertEqual(pre["hooks"][0]["timeout"], 20)
        for event in HOOK_EVENTS:
            self.assertIn(event, data["hooks"], event)
        report = doctor_checks.doctor(self.root)
        oks = [message for level, message in report if level == "ok" and message.startswith("Grok Build: the guard hook")]
        self.assertEqual(len(oks), 1, report)
        self.assertTrue(agent.is_file(), "developer agent missing")
        self.assertTrue(skill.is_file(), "implement skill missing")
        uninstalling.uninstall(self.root, yes=True)
        self.assertFalse(path.exists())
        self.assertFalse(agent.exists())
        self.assertFalse(skill.exists())

    def test_windows_writes_no_sh_hook(self):
        from aidd.setup import grok_wiring, hooks_file

        with mock.patch.object(hooks_file.os, "name", "nt"):
            actions: list[str] = []
            grok_wiring.install(self.root, actions)
        self.assertFalse((self.root / ".grok" / "hooks" / "aidd.json").exists())
        self.assertTrue(any("Windows" in action for action in actions), actions)


class SessionHookTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_repo(Path(tmp.name).resolve() / "repo", "team")
        (self.root / "specs").mkdir(parents=True, exist_ok=True)
        (self.root / "specs" / "S-1.md").write_text(SPEC, encoding="utf-8")

    def test_session_start_returns_a_top_level_system_message(self):
        event = {
            "hookEventName": "session_start",
            "hook_event_name": "SessionStart",
            "sessionId": "4f1c2d3e-0000-4000-8000-000000000001",
            "cwd": str(self.root),
            "workspaceRoot": str(self.root),
        }
        out = io.StringIO()
        self.assertEqual(session_hooks.run_session_hook("session-start", io.StringIO(json.dumps(event)), out, io.StringIO()), 0)
        answer = json.loads(out.getvalue())
        self.assertIn("S-1", answer["systemMessage"])
        self.assertNotIn("hookSpecificOutput", answer)

    def event(self, name: str, **extra) -> dict:
        return {"hookEventName": name, "sessionId": "4f1c2d3e-0000-4000-8000-000000000001", "cwd": str(self.root), "workspaceRoot": str(self.root)} | extra

    def call(self, hook: str, event: dict) -> str:
        out = io.StringIO()
        self.assertEqual(session_hooks.run_session_hook(hook, io.StringIO(json.dumps(event)), out, io.StringIO()), 0)
        return out.getvalue()

    def test_a_stop_continues_once_and_never_after_grok_says_a_hook_continued_it(self):
        (self.root / "src" / "app").mkdir(parents=True, exist_ok=True)
        (self.root / "src" / "app" / "x.py").write_text("print('hi')\n", encoding="utf-8")
        self.assertIn(session_hooks.TEST_REMINDER, self.call("stop", self.event("stop", hook_event_name="Stop", stopHookActive=False)))
        # Grok's camelCase flag: the hook already continued the agent this turn, so it lets the stop through.
        self.assertEqual(self.call("stop", self.event("stop", hook_event_name="Stop", stopHookActive=True)), "")

    def test_the_prompt_line_is_not_computed_where_grok_drops_it(self):
        self.assertEqual(self.call("prompt-submit", self.event("user_prompt_submit", hook_event_name="UserPromptSubmit")), "")


class GrokFileToolTests(unittest.TestCase):
    def test_every_file_edit_tool_and_the_cursor_presets_reach_the_guard(self):
        for name, args, want in (
            ("hashline_edit", {"file_path": "a.py"}, "Edit"),
            ("StrReplace", {"path": "a.py"}, "Edit"),
            ("Shell", {"command": "gh pr merge 1"}, "Bash"),
        ):
            out = dialects.of({"hookEventName": "pre_tool_use", "toolName": name, "toolInput": args}).normalize(
                {"hookEventName": "pre_tool_use", "toolName": name, "toolInput": args}
            )
            self.assertEqual(out["tool_name"], want, name)

    def test_a_flow_skill_is_a_slash_command_and_grok_fills_its_arguments(self):
        skill = team_install.team_files(["grok-build"], claude_files=False)[".grok/skills/aidd-fix/SKILL.md"]
        self.assertTrue(skill.startswith("---\nname: aidd-fix\ndescription: "), skill[:80])
        self.assertIn("\nuser-invocable: true\n---\n", skill)
        self.assertNotIn("stands for what the person typed", skill)  # Grok expands $ARGUMENTS itself


class ModelTests(unittest.TestCase):
    def test_an_xai_model_is_the_bare_name(self):
        self.assertEqual(agent_models.HARNESS_PROVIDER["grok-build"], "xai")
        self.assertEqual(agent_models.harness_model("grok-build", "xai/grok-4.7"), "grok-4.7")
        self.assertIsNone(agent_models.harness_model("grok-build", "anthropic/claude-sonnet-5"))

    def test_a_foreign_model_is_omitted_from_the_agent_file(self):
        foreign = team_install.team_files(["grok-build"], False, {"execution": "anthropic/claude-sonnet-5"})
        text = foreign[".grok/agents/aidd-developer.md"]
        self.assertNotRegex(text, r"(?m)^model:")
        self.assertIn("cannot select", text)
        own = team_install.team_files(["grok-build"], False, {"execution": "xai/grok-4.7"})
        self.assertRegex(own[".grok/agents/aidd-developer.md"], r"(?m)^model: grok-4\.7$")
