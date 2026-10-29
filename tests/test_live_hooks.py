"""`aidd eval hooks`: the live check of a harness's hook events, and the replay of the events it pinned.

Each file in tests/fixtures/live/ holds the events one real session of a harness sent, masked, with what aidd's
dialect read from each tool call when it was recorded. The replay fails when a dialect change reads a real event
another way, so a change to a dialect meets the harness as it is, not only the shapes its documentation describes.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT

from aidd import config
from aidd.guard import dialects, live_hooks, role_areas

LIVE = ROOT / "tests" / "fixtures" / "live"


def antigravity(tool: dict | None = None, conversation: str = "main", **extra) -> dict:
    event = {"conversationId": conversation, "workspacePaths": ["/w"], **extra}
    return {**event, "toolCall": tool} if tool else event


class ReplayTests(unittest.TestCase):
    def home(self, fixture: Path, stack: contextlib.ExitStack) -> Path:
        """A scratch home with the Antigravity messages pinned beside a fixture, oldest first, as they were live; an
        empty one for any other fixture, so no replay reads this machine's own records."""
        home = Path(stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        pinned = fixture.with_name(fixture.stem + ".messages.json")
        for conversation, files in (json.loads(pinned.read_text(encoding="utf-8")) if pinned.is_file() else {}).items():
            folder = home / ".gemini" / "antigravity-cli" / "brain" / conversation / ".system_generated" / "messages"
            folder.mkdir(parents=True)
            for n, item in enumerate(files):
                (folder / item["name"]).write_text(json.dumps(item["message"]), encoding="utf-8")
                os.utime(folder / item["name"], (1_000_000 + n, 1_000_000 + n))
        stack.enter_context(mock.patch.dict(os.environ, {"HOME": str(home), "USERPROFILE": str(home)}))
        return home

    def test_every_pinned_event_reads_as_it_did_live(self):
        files = sorted(LIVE.glob("*.jsonl"))
        self.assertTrue(files, "no live run is pinned: run `aidd eval hooks`")
        for f in files:
            with self.subTest(file=f.name), contextlib.ExitStack() as stack:
                self.home(f, stack)
                for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                    pinned = json.loads(line)
                    if "reads_as" in pinned:
                        with self.subTest(line=n):
                            self.assertEqual(live_hooks.reading(pinned["event"]), pinned["reads_as"])

    def test_claude_code_names_a_subagent_by_its_id_and_a_main_thread_by_none(self):
        """Pinned live in Claude Code 2.1.311: a subagent's events carry `agent_id` beside `agent_type`; a main
        thread run with `--agent` carries `agent_type` alone, and reads as the main thread."""
        sub = [json.loads(line)["event"] for line in (LIVE / "claude-code-2.1.311.jsonl").read_text(encoding="utf-8").splitlines()]
        roled = [e for e in sub if e.get("agent_type")]
        self.assertTrue(roled and all(e.get("agent_id") for e in roled), "every subagent event names its id")
        self.assertIn("SubagentStart", {e.get("hook_event_name") for e in roled})
        main = [json.loads(line)["event"] for line in (LIVE / "claude-code-2.1.311-agent.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertTrue(main and all(e.get("agent_type") == "aidd-architect" and not e.get("agent_id") for e in main))
        calls = [e for e in main if e.get("hook_event_name") == "PreToolUse"]  # the start rule reads tool calls only
        self.assertTrue(calls and all(role_areas.is_main_thread(dialects.of(e).normalize(e)) for e in calls))
        self.assertFalse(any(role_areas.is_main_thread(dialects.of(e).normalize(e)) for e in roled))

    def test_antigravity_holds_each_role_of_a_real_autopilot_run(self):
        """Antigravity's autopilot ran SPEC-1 to Merge approval with the team, each role a subagent conversation
        whose events name no parent. The guard read every role from the parent's message, and none in the main session."""
        f = LIVE / "antigravity-1.4.7-roles.jsonl"
        self.home(f, self.enterContext(contextlib.ExitStack()))
        captured = [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines()]
        verdicts = {name: (verdict, seen) for name, verdict, seen in live_hooks.judge("antigravity", captured)}
        self.assertEqual(verdicts["a subagent carries its role"][0], "ok", verdicts)
        self.assertEqual(verdicts["the main session carries no role"][0], "ok", verdicts)
        roles = {c["reads_as"]["agent_type"] for c in captured if c.get("reads_as")} - {""}
        self.assertEqual(roles, {"aidd-architect", "aidd-verifier", "aidd-developer", "aidd-reviewer"})

    def test_no_pinned_message_holds_a_home_folder_or_a_prompt(self):
        prompts = ("content", "Prompt", "Message")
        for f in LIVE.glob("*.messages.json"):
            text = f.read_text(encoding="utf-8")
            for home in ("/Users/", "/home/", "C:\\Users", str(Path.home())):
                self.assertNotIn(home, text, f.name)
            for conversation, files in json.loads(text).items():
                for item in files:
                    message = item["message"]
                    self.assertLessEqual(set(message), {*live_hooks._MESSAGE_FIELDS, "content", "renderDetails", "sourceMetadata"})
                    self.assertIn(message.get("content", "<prompt>"), ("<prompt>", ""), f"{f.name}: {conversation}")
                    call = (message.get("sourceMetadata") or {}).get("tool", {}).get("toolCall") or {}
                    self.assertNotIn("thinkingSignature", call)
                    args = json.loads(call.get("argumentsJson") or "{}")
                    self.assertEqual({k: v for k, v in args.items() if k in prompts}, dict.fromkeys(set(args) & set(prompts), "<prompt>"))

    def test_eval_hooks_pins_each_conversations_messages_oldest_first(self):
        """What the replay restores is what `aidd eval hooks` writes: the messages, the prompts masked, the signature dropped."""
        scratch = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        folder = scratch / ".gemini" / "antigravity-cli" / "brain" / "child"
        (folder / ".system_generated" / "messages").mkdir(parents=True)
        call = {"name": "invoke_subagent", "thinkingSignature": "x", "argumentsJson": json.dumps({"Prompt": f"edit {scratch}/a", "TypeName": "aidd-developer"})}
        for n, name in enumerate(("b.json", "a.json")):
            message = {"recipient": "child", "content": "do it", "extra": "x", "sourceMetadata": {"tool": {"toolCall": dict(call)}}}
            (folder / ".system_generated" / "messages" / name).write_text(json.dumps(message), encoding="utf-8")
            os.utime(folder / ".system_generated" / "messages" / name, (1_000 + n, 1_000 + n))
        event = {"conversationId": "child", "artifactDirectoryPath": str(folder)}
        pinned = live_hooks.antigravity_messages([{"hook": "pre-tool", "event": event}], scratch)
        self.assertEqual([item["name"] for item in pinned["child"]], ["b.json", "a.json"])
        message = pinned["child"][0]["message"]
        self.assertEqual(set(message), {"recipient", "content", "sourceMetadata"}, "only the fields the role reading needs")
        self.assertEqual(message["content"], "<prompt>")
        self.assertEqual(
            message["sourceMetadata"]["tool"]["toolCall"], {"name": "invoke_subagent", "argumentsJson": '{"Prompt": "<prompt>", "TypeName": "aidd-developer"}'}
        )

    def test_no_pinned_event_holds_a_home_folder_or_a_prompt(self):
        for f in LIVE.glob("*.jsonl"):
            text = f.read_text(encoding="utf-8")
            for home in ("/Users/", "/home/", "C:\\Users", str(Path.home())):
                self.assertNotIn(home, text, f.name)
            for line in text.splitlines():
                event = json.loads(line)["event"]
                for key in ("lastUserInput", "prompt"):
                    if isinstance(event, dict) and key in event:
                        self.assertEqual(event[key], "<prompt>", f"{f.name}: {key}")


class JudgeTests(unittest.TestCase):
    def captured(self, *events: tuple[str, dict]) -> list[dict]:
        return [{"hook": hook, "event": event} for hook, event in events]

    def verdicts(self, *events) -> dict[str, str]:
        return {name: verdict for name, verdict, _ in live_hooks.judge("antigravity", self.captured(*events))}

    def test_a_clean_session(self):
        write = {"name": "write_file", "args": {"Path": "/w/a.md", "Content": "x"}}
        sub = {"name": "write_file", "args": {"Path": "/w/b.md", "Content": "y"}}
        mcp = {"name": "mcp_tool", "args": {"ServerName": "aidd_aidd", "ToolName": "validate", "Arguments": "{}"}}
        got = self.verdicts(
            ("session-start", antigravity()),
            ("pre-tool", antigravity(write)),
            ("pre-tool", antigravity(mcp)),
            ("pre-tool", antigravity(sub, conversation="child", agentName="aidd-developer", parentConversationId="main")),
        )
        self.assertEqual(set(got.values()), {"ok"}, got)

    def test_a_role_in_the_main_session_fails(self):
        write = {"name": "write_file", "args": {"Path": "/w/a.md", "Content": "x"}}
        got = self.verdicts(("session-start", antigravity()), ("pre-tool", antigravity(write, agentName="self")))
        self.assertEqual(got["the main session carries no role"], "fail")

    def test_claude_code_names_a_subagent_by_its_id_within_the_session(self):
        """Claude Code keeps one session and names a subagent by `agent_id`: a subagent's call is never the main
        session's, and a tool that is no file write (TodoWrite, an MCP check) is not judged as one."""

        def claude(**extra) -> dict:
            return {"session_id": "s1", "hook_event_name": "PreToolUse", "cwd": "/w", **extra}

        got = {
            name: verdict
            for name, verdict, _ in live_hooks.judge(
                "claude-code",
                self.captured(
                    ("session-start", {"session_id": "s1", "hook_event_name": "SessionStart", "cwd": "/w", "source": "startup"}),
                    ("pre-tool", claude(tool_name="Write", tool_input={"file_path": "/w/a.md", "content": "x"})),
                    ("pre-tool", claude(tool_name="TodoWrite", tool_input={"todos": []})),
                    ("pre-tool", claude(tool_name="mcp__aidd__check_edit", tool_input={"path": "a.md"})),
                    (
                        "pre-tool",
                        claude(tool_name="Write", tool_input={"file_path": "/w/b.md", "content": "y"}, agent_id="a1", agent_type="aidd-team:developer"),
                    ),
                ),
            )
        }
        self.assertEqual(set(got.values()), {"ok"}, got)

    def test_grok_build_names_its_session_and_tool_its_own_way(self):
        def grok(**extra) -> dict:
            return {"hookEventName": "PreToolUse", "sessionId": "g1", "workspaceRoot": "/w", **extra}

        got = {
            name: verdict
            for name, verdict, _ in live_hooks.judge(
                "grok-build",
                self.captured(
                    ("session-start", {"hookEventName": "SessionStart", "sessionId": "g1", "workspaceRoot": "/w"}),
                    ("pre-tool", grok(toolName="write", toolInput={"path": "/w/a.md", "contents": "x"})),
                    ("pre-tool", grok(toolName="write", toolInput={"path": "/w/b.md", "contents": "y"}, sessionId="g2", subagentType="aidd-developer")),
                ),
            )
        }
        self.assertEqual(got["the main session carries no role"], "ok")
        self.assertEqual(got["a subagent carries its role"], "ok")
        self.assertEqual(got["each file write reads as an edit of its path"], "ok")

    def test_a_harness_whose_events_name_no_subagent_is_a_known_limit_there_only(self):
        """Codex's tool events name no subagent: a call from another session there is SECURITY.md's known limit. The
        same in a harness whose events name a subagent (Claude Code, Antigravity) fails."""

        def codex(session: str) -> dict:
            return {"session_id": session, "turn_id": "t1", "hook_event_name": "PreToolUse", "cwd": "/w", "tool_name": "Bash", "tool_input": {"command": "ls"}}

        got = {n: v for n, v, _ in live_hooks.judge("codex", self.captured(("pre-tool", codex("c1")), ("pre-tool", codex("c2"))))}
        self.assertEqual(got["a subagent carries its role"], "limit")
        write = {"name": "write_file", "args": {"Path": "/w/b.md", "Content": "y"}}
        got = self.verdicts(("session-start", antigravity()), ("pre-tool", antigravity(write, conversation="child")))
        self.assertEqual(got["a subagent carries its role"], "fail", "Antigravity names its subagents now: one with no parent message is a failure")

    def test_what_the_run_did_not_reach_is_unseen_never_passed(self):
        got = self.verdicts(("session-start", antigravity()))
        self.assertEqual(got["hooks ran"], "fail")
        self.assertEqual(got["a subagent carries its role"], "unseen")
        self.assertEqual(got["an MCP call names aidd's server"], "unseen")


class ScratchTests(unittest.TestCase):
    def test_every_guarded_harness_starts_the_aidd_under_test(self):
        """No file in the scratch repository starts the person's launcher, in any harness aidd guards."""
        for harness in [h.key for h in config.guarded_harnesses()]:
            with self.subTest(harness=harness), tempfile.TemporaryDirectory() as tmp:
                repo = live_hooks.scratch(Path(tmp).resolve(), harness, ROOT / "src")
                for path in (p for p in repo.rglob("*") if p.is_file() and ".git" not in p.relative_to(repo).parts):
                    text = path.read_text(encoding="utf-8", errors="replace")
                    self.assertNotIn(".aidd/bin/aidd", text, path.relative_to(repo))
                    self.assertNotIn(live_hooks.JS_LAUNCHER, text, path.relative_to(repo))

    def test_a_harness_aidd_does_not_guard_is_named(self):
        with self.assertRaisesRegex(ValueError, "has no hooks to check"):
            live_hooks.eval_hooks(ROOT, "cursor", "true", 5)

    def test_the_scratch_hooks_run_the_aidd_under_test_and_init_never_touches_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp).resolve()
            before = os.environ.get("HOME")
            repo = live_hooks.scratch(dest, "antigravity", ROOT / "src")
            self.assertEqual(os.environ.get("HOME"), before)
            hooks = (repo / ".agents" / "hooks.json").read_text(encoding="utf-8")
            self.assertIn(str(dest / "aidd-under-test"), hooks)
            self.assertNotIn(".aidd/bin/aidd", hooks)
            self.assertTrue((dest / "home" / ".aidd" / "bin" / "aidd").exists())  # init's launcher went to the scratch home
            launcher = (dest / "aidd-under-test").read_text(encoding="utf-8")
            self.assertIn(f'AIDD_HOOK_CAPTURE="{dest / live_hooks.CAPTURE}"', launcher)

    def test_masking_drops_the_prompt_and_the_folders(self):
        dest = Path("/tmp/aidd-live-x")
        event = antigravity({"name": "write_file", "args": {"Path": f"{dest}/repo/a.md", "Content": "x"}}, lastUserInput="secret words")
        event["transcriptPath"] = f"{Path.home()}/.gemini/t.jsonl"
        [line] = live_hooks.masked([{"hook": "pre-tool", "event": event}], dest)
        self.assertEqual(line["event"]["lastUserInput"], "<prompt>")
        self.assertEqual(line["event"]["toolCall"]["args"]["Path"], "<scratch>/repo/a.md")
        self.assertEqual(line["event"]["transcriptPath"], "~/.gemini/t.jsonl")
        self.assertEqual(line["reads_as"]["tool_name"], "Write")


if __name__ == "__main__":
    unittest.main()
