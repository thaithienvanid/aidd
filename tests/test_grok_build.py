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
from aidd.guard import approval_commands, dialects, pending_notes, pre_tool, session_hooks
from aidd.knowledge import agent_models
from aidd.setup import adoption, doctor_checks, harness_text, team_install, uninstalling

READ_ONLY = frozenset({"reviewer", "domain-expert"})
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
        self.assertGreaterEqual(len(agents), 13)
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

    def test_an_unknown_tool_is_denied_here_and_left_alone_where_aidd_is_not_adopted(self):
        """Fail closed: a Grok tool the guard does not know may write anything, so it is denied in a repository that
        adopted aidd, with what to use instead. The aidd plugin's guard also runs in Grok sessions elsewhere, where aidd
        does nothing."""
        denied = json.loads(guard_stdout(self.root, "image_gen", {"prompt": "a cat"}))["hookSpecificOutput"]
        self.assertEqual(denied["permissionDecision"], "deny")
        self.assertIn("use the shell, edit, or write tool instead", denied["permissionDecisionReason"])
        self.assertEqual(guard_stdout(self.root, "read_file", {"target_file": "README.md"}), "")
        with tempfile.TemporaryDirectory() as other:
            git(Path(other), "init", "-q")
            self.assertEqual(guard_stdout(Path(other), "image_gen", {"prompt": "a cat"}), "")
            # A session outside the repository, whose tool names a path inside it, is still denied, and so is one whose
            # input is too large to read through.
            inside = {"prompt": "a cat", "options": {"output_path": str(self.root / "docs" / "cat.png")}}
            self.assertEqual(permission(guard_stdout(Path(other), "image_gen", inside)), "deny")
            self.assertEqual(permission(guard_stdout(Path(other), "image_gen", {"paths": ["x"] * 100})), "deny")
            # A call whose fields name two different files is never left alone either, and says what to do.
            twice = guard_stdout(Path(other), "Write", {"path": "a.py", "file_path": str(self.root / ".aidd" / "config.yaml"), "contents": "x"})
            self.assertIn("run it again with each named once", json.loads(twice)["hookSpecificOutput"]["permissionDecisionReason"])
            # A shell command the guard cannot read is never left alone, in or out of a repository.
            self.assertEqual(permission(guard_stdout(Path(other), "run_terminal_command", {"command": ["ls"]})), "deny")

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
            # This repository writes `mode: enforce`, which fails closed (repo_config.fails_closed); advising, it does not.
            self.assertEqual(json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecision"], "deny")
            cfg = self.root / ".aidd" / "config.yaml"
            cfg.write_text(cfg.read_text(encoding="utf-8").replace("\nmode: enforce", "\nmode: advisory"), encoding="utf-8")
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

    def test_a_recorded_decision_reaches_the_agent_on_its_next_tool_call_or_stop(self):
        # Grok drops the prompt hook's line, so the agent, told "approve S-1", would ask the person again (a live run).
        def prompt(event):
            out = io.StringIO()
            session_hooks.run_session_hook(
                "prompt-submit", io.StringIO(json.dumps(event)), out, io.StringIO(), on_prompt=lambda text, root, session_id: "aidd recorded S-1"
            )

        sid = "4f1c2d3e-0000-4000-8000-000000000001"
        prompt(self.event("user_prompt_submit", hook_event_name="UserPromptSubmit", prompt="approve S-1"))
        first = guard_stdout(self.root, "run_terminal_command", {"command": "ls"}, sessionId=sid)
        self.assertIn("aidd recorded S-1", json.loads(first)["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(guard_stdout(self.root, "run_terminal_command", {"command": "ls"}, sessionId=sid), "")  # once
        prompt(self.event("user_prompt_submit", hook_event_name="UserPromptSubmit", prompt="approve S-1"))
        stop = json.loads(self.call("stop", self.event("stop", hook_event_name="Stop", stopHookActive=False)))
        self.assertEqual((stop["decision"], stop["reason"]), ("block", "aidd recorded S-1"))  # no tool call came: the stop says it
        denied = guard_stdout(self.root, "run_terminal_command", {"command": "gh pr merge 1"}, sessionId=sid)
        self.assertNotIn("aidd recorded S-1", denied)  # delivered once, never again
        prompt(self.event("user_prompt_submit", hook_event_name="UserPromptSubmit", prompt="approve S-1"))
        with mock.patch.object(pending_notes, "take", side_effect=OSError("disk")):  # a note that cannot be read
            self.assertIn('"deny"', guard_stdout(self.root, "run_terminal_command", {"command": "gh pr merge 1"}, sessionId=sid))

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

    @staticmethod
    def normal(name: str, args: dict) -> dict:
        event = {"hookEventName": "pre_tool_use", "toolName": name, "toolInput": args, "workspaceRoot": "/tmp/repo"}
        return dialects.of(event).normalize(event)

    def test_the_daemon_routes_file_tools_name_their_file_where_the_guard_reads_it(self):
        """grok 1.0.62's hooks guide: `StrReplace` and `Write` name the file in `path`, `Write` holds its text in
        `contents`, and `EditNotebook` names the notebook in `target_notebook`; `Delete` removes a file."""
        cases = {
            ("Write", ("path", "contents")): ("Write", {"file_path": "a.py", "content": "x"}),
            ("StrReplace", ("path",)): ("Edit", {"file_path": "a.py"}),
            ("EditNotebook", ("target_notebook",)): ("Edit", {"file_path": "a.py"}),
            ("Delete", ("path",)): ("Edit", {"file_path": "a.py"}),
            ("FetchMcpResource", ("downloadPath",)): ("Write", {"file_path": "a.py"}),
        }
        for (name, keys), (tool, want) in cases.items():
            with self.subTest(name):
                args = {k: "x" if k == "contents" else "a.py" for k in keys}
                out = self.normal(name, args)
                self.assertEqual(out["tool_name"], tool)
                self.assertEqual({k: out["tool_input"][k] for k in want}, want)
                self.assertNotIn("opaque_tool", out)
        patch = self.normal("apply_patch", {"input": "*** Begin Patch\n*** Add File: a.py\n+x\n*** End Patch"})
        self.assertEqual((patch["tool_name"], patch["tool_input"]["command"][:15]), (dialects.APPLY_PATCH, "*** Begin Patch"))

    def test_a_call_that_names_its_file_text_or_patch_twice_and_differently_is_denied(self):
        """The harness reads one field, and the guard cannot tell which: two that disagree deny the call. Two that agree
        are one file."""
        patch = "*** Begin Patch\n*** Add File: a.py\n+x\n*** End Patch"
        for name, args in (
            ("StrReplace", {"path": "a.py", "file_path": ".aidd/config.yaml", "old_string": "a", "new_string": "b"}),
            ("EditNotebook", {"target_notebook": "a.ipynb", "path": ".git/config"}),
            ("Write", {"path": "a.py", "contents": "x", "content": "y"}),
            ("apply_patch", {"input": patch, "patch": patch.replace("a.py", ".git/config")}),
        ):
            with self.subTest(name):
                out = self.normal(name, args)
                self.assertEqual(out["opaque_tool"], dialects.AMBIGUOUS_CALL)
                self.assertFalse(out["unknown_tool"], "denied everywhere, never left alone outside a repository")
        same = self.normal("Write", {"path": "a.py", "file_path": "a.py", "contents": "x", "content": "x"})
        self.assertEqual((same["tool_input"]["file_path"], same["tool_input"]["content"]), ("a.py", "x"))
        self.assertNotIn("opaque_tool", same)
        # OpenCode reads its edit's file and its patch the same way.
        for tool, args in (
            ("edit", {"path": "a.py", "filePath": ".git/config", "oldString": "a", "newString": "b"}),
            ("apply_patch", {"patchText": patch, "patch": "x"}),
        ):
            with self.subTest(opencode=tool):
                event = {"harness": "opencode", "tool": tool, "input": args, "sessionID": "ses_1", "cwd": "/tmp/repo"}
                self.assertEqual(dialects.OPENCODE.normalize(event)["opaque_tool"], dialects.AMBIGUOUS_CALL)

    def test_every_tool_a_live_session_used_reads_or_reaches_a_check(self):
        """The tools past grok sessions on this machine called (their names and input keys, from
        ~/.grok/sessions/*/updates.jsonl): each read reaches no check, and every other one is mapped."""
        reads = ("read_file", "grep", "list_dir", "web_search", "web_fetch", "todo_write", "spawn_subagent", "search_tool")
        reads += ("get_command_or_subagent_output", "kill_command_or_subagent", "ask_user_question")
        for name in reads:
            with self.subTest(name):
                out = self.normal(name, {"target_file": "a.py"})
                self.assertNotIn("tool_name", out)
                self.assertNotIn("opaque_tool", out)

    def test_a_tool_the_guard_does_not_know_or_cannot_read_is_marked(self):
        for name, args in (("image_gen", {"prompt": "a cat"}), ("execute", {"code": "x"}), ("monitor", {"command": "ls"}), ("Delete", {})):
            with self.subTest(name):
                self.assertIn(f"`{name}` is a tool the guard does not know", self.normal(name, args)["opaque_tool"])

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
