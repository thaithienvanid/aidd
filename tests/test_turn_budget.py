"""The turn budget: a wrap-up line before an aidd-team role's turn cap, and one hold of a role's stop with no handoff note.

`aidd hook post-tool` (Claude Code's PostToolUse) counts a role's tool calls by `agent_id`, and tells it at about 80% and
95% of its `maxTurns` to wrap up. `aidd hook stop` holds a SubagentStop whose last message has no `aidd-handoff` block, once.
"""

import io
import json
import os
import subprocess
import time
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT, RepoTemplateCase, make_repo

from aidd import knowledge
from aidd.guard import dialects, session_hooks, turn_budget
from aidd.setup import hook_gate, hook_wiring

ROLE = "aidd-team:developer"
HANDOFF = "Done.\n\n```aidd-handoff\ndone: a change\nnext: reviewer\nneeds: none\nstopped_at: none\nspend: unknown\n```"
HOLD = "aidd: please add your handoff note before you stop (an `aidd-handoff` block: Done, Next, Needs, Stopped at, Spend)."


def cap_of(role: str) -> int:
    return knowledge.roles()["roles"][role]["max_turns"]


class ThresholdTests(unittest.TestCase):
    def test_the_lines_come_at_eighty_and_ninety_five_percent(self):
        self.assertEqual(turn_budget.thresholds(100), (80, 95))
        self.assertEqual(turn_budget.thresholds(150), (120, 143))
        self.assertEqual(turn_budget.thresholds(1), (1, 1))

    def test_the_words(self):
        self.assertEqual(
            turn_budget.wrap_up_line(80, 100),
            "aidd: you have used about 80 of your 100 turns. Finish the step you are on, then write your handoff note and report what is left.",
        )
        self.assertEqual(turn_budget.stop_line(5), "aidd: about 5 turns are left. Finish here: write your handoff note and report what is left.")

    def test_every_role_has_a_cap(self):
        for role, data in knowledge.roles()["roles"].items():
            self.assertIsInstance(data.get("max_turns"), int, role)


class PostToolTests(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        make_repo(root, "team")

    def call(self, agent_id="a1", agent_type=ROLE, **extra) -> str:
        event = {
            "hook_event_name": "PostToolUse",
            "session_id": "s1",
            "transcript_path": "/tmp/s1.jsonl",
            "permission_mode": "default",
            "cwd": str(self.root),
            "tool_name": "Read",
            "tool_input": {},
            "tool_response": {},
            **extra,
        }
        if agent_id is not None:
            event["agent_id"] = agent_id
        if agent_type is not None:
            event["agent_type"] = agent_type
        out, err = io.StringIO(), io.StringIO()
        self.assertEqual(turn_budget.post_tool_hook(io.StringIO(json.dumps(event)), out, err), 0, err.getvalue())
        self.assertEqual(err.getvalue(), "")
        return out.getvalue()

    def said(self, out: str) -> str:
        return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else ""

    def run_calls(self, n: int, **kw) -> list[str]:
        return [self.said(self.call(**kw)) for _ in range(n)]

    def test_each_line_comes_once_at_its_threshold(self):
        cap = cap_of("developer")
        first, last = turn_budget.thresholds(cap)
        lines = self.run_calls(cap + 5)
        said = {i + 1: line for i, line in enumerate(lines) if line}
        self.assertEqual(sorted(said), [first, last])
        self.assertEqual(said[first], turn_budget.wrap_up_line(first, cap))
        self.assertEqual(said[last], turn_budget.stop_line(cap - last))

    def test_a_test_cap_only_lowers_a_role_s_cap(self):
        with mock.patch.dict("os.environ", {turn_budget.CAP_ENV: "5"}):
            lines = self.run_calls(8)
        self.assertEqual([i + 1 for i, line in enumerate(lines) if line], [4, 5])
        self.assertEqual(lines[3], turn_budget.wrap_up_line(4, 5))
        with mock.patch.dict("os.environ", {turn_budget.CAP_ENV: "100000"}):
            self.assertEqual(self.run_calls(10, agent_id="big"), [""] * 10)

    def test_the_live_check_reads_the_count_files(self):
        from aidd.guard import live_hooks

        event = {"agent_id": "a1", "agent_type": "aidd-developer"}
        captured = [{"hook": "post-tool", "event": event}]
        self.assertEqual(live_hooks._counted(captured, self.root)[0], "fail")  # events, and no count kept
        with mock.patch.dict("os.environ", {turn_budget.CAP_ENV: "5"}):
            self.run_calls(5, agent_type="aidd-developer")
        self.assertEqual(live_hooks._counted(captured, self.root)[0], "ok")
        self.assertEqual(live_hooks._counted([], self.root)[0], "unseen")

    def test_a_linked_turns_folder_is_never_followed(self):
        outside = self.root / "elsewhere"
        outside.mkdir()
        folder = Path(self.root, ".git", "aidd", turn_budget.FOLDER)
        folder.parent.mkdir(parents=True, exist_ok=True)
        folder.symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.run_calls(cap_of("developer")), [""] * cap_of("developer"))
        self.assertEqual(list(outside.iterdir()), [])

    def test_a_linked_cap_file_is_not_followed_and_pruning_leaves_other_names(self):
        folder = Path(self.root, ".git", "aidd", turn_budget.FOLDER)
        folder.mkdir(parents=True)
        target = self.root / "victim.txt"
        target.write_text("keep", encoding="utf-8")
        (folder / "lk.cap").symlink_to(target)
        self.call(agent_id="lk")  # the registry is read again, and the write refuses the link
        self.assertEqual(target.read_text(encoding="utf-8"), "keep")
        (folder / "notes.txt").write_text("mine", encoding="utf-8")
        (folder / "link.n").symlink_to(target)
        for i in range(turn_budget.MAX_FILES + 20):
            (folder / f"old{i}.n").write_bytes(b".")
        self.call(agent_id="fresh")
        self.assertTrue((folder / "notes.txt").exists())
        self.assertTrue((folder / "link.n").is_symlink())
        self.assertEqual(target.read_text(encoding="utf-8"), "keep")

    def test_the_answer_is_a_post_tool_context(self):
        first, _ = turn_budget.thresholds(cap_of("developer"))
        out = [self.call() for _ in range(first)][-1]
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["hookEventName"], "PostToolUse")

    def test_past_both_thresholds_at_once_only_the_stop_line_comes(self):
        cap = cap_of("developer")
        _, last = turn_budget.thresholds(cap)
        state = Path(self.root, ".git", "aidd", turn_budget.FOLDER)
        state.mkdir(parents=True)
        (state / "late.n").write_bytes(b"." * (last - 1))
        (state / "late.cap").write_text(str(cap), encoding="ascii")
        self.assertEqual(self.said(self.call(agent_id="late")), turn_budget.stop_line(cap - last))
        self.assertEqual(self.run_calls(10, agent_id="late"), [""] * 10)

    def test_each_agent_counts_apart(self):
        cap = cap_of("developer")
        first, _ = turn_budget.thresholds(cap)
        self.run_calls(first - 1, agent_id="one")
        self.assertEqual(self.run_calls(first - 1, agent_id="two"), [""] * (first - 1))
        self.assertEqual(self.said(self.call(agent_id="one")), turn_budget.wrap_up_line(first, cap))

    def test_the_cap_follows_the_role(self):
        cap = cap_of("reviewer")
        first, _ = turn_budget.thresholds(cap)
        lines = self.run_calls(first, agent_type="aidd-team:reviewer")
        self.assertEqual(lines[-1], turn_budget.wrap_up_line(first, cap))
        project_role = self.run_calls(first, agent_id="b2", agent_type="aidd-reviewer")
        self.assertEqual(project_role[-1], turn_budget.wrap_up_line(first, cap))

    def test_the_lead_a_helper_and_a_name_that_is_no_role_cost_nothing(self):
        folder = Path(self.root, ".git", "aidd", turn_budget.FOLDER)
        for kw in ({"agent_id": None, "agent_type": None}, {"agent_id": None}, {"agent_type": "Explore"}, {"agent_type": "general-purpose"}):
            self.assertEqual(self.run_calls(200, **kw), [""] * 200, kw)
        self.assertEqual(self.run_calls(200, agent_id="c3", agent_type="aidd-not-a-role"), [""] * 200)
        self.assertEqual([p.name for p in folder.glob("*") if p.suffix == ".n" and p.stem != "c3"], [])

    def test_a_harness_that_names_no_subagent_gets_nothing(self):
        for event in (
            {
                "harness": "opencode",
                "tool": "read",
                "input": {},
                "sessionID": "s",
                "agent": "aidd-developer",
                "cwd": str(self.root),
                "agent_id": "x",
                "agent_type": ROLE,
            },
            {"turn_id": "t", "agent_id": "x", "agent_type": ROLE, "cwd": str(self.root), "hook_event_name": "PostToolUse"},
            {"toolCall": {"name": "x", "args": {}}, "conversationId": "c", "agent_id": "x", "agent_type": ROLE, "cwd": str(self.root)},
        ):
            self.assertFalse(dialects.of(event).counts_turns, event)
            out = io.StringIO()
            for _ in range(300):
                turn_budget.post_tool_hook(io.StringIO(json.dumps(event)), out, io.StringIO())
            self.assertEqual(out.getvalue(), "")
        self.assertTrue(dialects.CLAUDE_CODE.counts_turns)

    def test_hooks_off_say_nothing(self):
        cfg = self.root / ".aidd" / "config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + "\nhooks:\n  level: off\n", encoding="utf-8")
        self.assertEqual(self.run_calls(cap_of("developer")), [""] * cap_of("developer"))

    def test_a_repository_that_never_adopted_aidd_gets_nothing(self):
        (self.root / ".aidd" / "config.yaml").unlink()
        self.assertEqual(self.run_calls(cap_of("developer")), [""] * cap_of("developer"))

    def test_an_internal_error_allows(self):
        out, err = io.StringIO(), io.StringIO()
        self.assertEqual(turn_budget.post_tool_hook(io.StringIO("not json"), out, err), 0)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("skipped after an internal error", err.getvalue())

    def test_an_agent_id_that_is_a_path_is_never_used(self):
        self.assertEqual(self.run_calls(3, agent_id="../../x"), [""] * 3)
        self.assertFalse(Path(self.root, ".git", "x.n").exists())

    def test_the_count_folder_keeps_at_most_a_set_number_of_files(self):
        folder = Path(self.root, ".git", "aidd", turn_budget.FOLDER)
        folder.mkdir(parents=True)
        for i in range(turn_budget.MAX_FILES + 20):
            (folder / f"old{i}.n").write_bytes(b".")
        self.call(agent_id="fresh")
        self.assertLessEqual(len(list(folder.iterdir())), turn_budget.MAX_FILES + 2)


class ShellGateTests(RepoTemplateCase):
    """The shell check before Python (setup/hook_gate.py), run as the plugin's hook runs it: `sh -c` of the command in
    hooks.json, with the event on stdin."""

    @classmethod
    def build_template(cls, root):
        make_repo(root, "team")

    def run_hook(self, event: dict | str, command: str | None = None) -> subprocess.CompletedProcess:
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        text = event if isinstance(event, str) else json.dumps({"hook_event_name": "PostToolUse", "cwd": str(self.root), "tool_name": "Read", **event})
        env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(ROOT), "CLAUDE_PROJECT_DIR": str(self.root)}
        return subprocess.run(
            ["/bin/sh", "-c", command or hooks["PostToolUse"][0]["hooks"][0]["command"]],
            input=text,
            capture_output=True,
            text=True,
            cwd=self.root,
            env=env,
            timeout=60,
        )

    def counted(self) -> list[str]:
        folder = Path(self.root, ".git", "aidd", turn_budget.FOLDER)
        return sorted(p.name for p in folder.glob("*.n")) if folder.is_dir() else []

    def test_the_lead_and_a_helper_end_at_the_shell_without_python(self):
        for event in ({}, {"agent_id": "h1", "agent_type": "Explore"}, {"agent_id": "h2", "agent_type": "general-purpose"}):
            done = self.run_hook(event)
            self.assertEqual((done.returncode, done.stdout, done.stderr), (0, "", ""), event)
        self.assertEqual(self.counted(), [])

    def test_a_role_goes_on_to_python_and_is_counted(self):
        for agent_type in ("aidd-team:developer", "aidd-developer"):
            done = self.run_hook({"agent_id": "r-" + str(len(agent_type)), "agent_type": agent_type})
            self.assertEqual((done.returncode, done.stderr), (0, ""), agent_type)
        self.assertEqual(len(self.counted()), 2)

    def test_the_wrap_up_line_reaches_the_role_through_the_pipe(self):
        cap = cap_of("developer")
        first, _ = turn_budget.thresholds(cap)
        folder = Path(self.root, ".git", "aidd", turn_budget.FOLDER)
        folder.mkdir(parents=True)
        (folder / "late.n").write_bytes(b"." * (first - 1))
        (folder / "late.cap").write_text(str(cap), encoding="ascii")
        done = self.run_hook({"agent_id": "late", "agent_type": ROLE})
        self.assertEqual(json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"], turn_budget.wrap_up_line(first, cap))

    def test_odd_input_is_data_and_never_runs(self):
        marker = self.root / "ran"
        nasty = {"agent_id": "n1", "agent_type": ROLE, "tool_response": f"$(touch {marker}) `touch {marker}` '; touch {marker}; ' \" \\ %s\n\u0000"}
        for event in (
            nasty,
            {k: v for k, v in nasty.items() if k != "agent_type"} | {"tool_response": f"$(touch {marker}) aidd-"},
            "not json at all $(touch " + str(marker) + ")",
            "",
        ):
            done = self.run_hook(event)
            self.assertEqual(done.returncode, 0, event)
        self.assertFalse(marker.exists())

    def test_the_settings_route_writes_the_same_check(self):
        command = hook_wiring.hook_command("post-tool", shell="sh")
        self.assertTrue(command.startswith(hook_gate.POST_TOOL_GATE), command)
        self.assertEqual(hook_wiring.aidd_hook(command), "post-tool")
        self.assertEqual(hook_wiring._hook_words(command)[0][-2:], ["hook", "post-tool"])
        self.assertFalse(hook_wiring.hook_command("stop", shell="sh").startswith("E="))
        done = self.run_hook({"agent_id": "s1"}, command=command.replace(hook_wiring.HOOK_LAUNCHER, "/usr/bin/false"))
        self.assertEqual(done.returncode, 0)  # a lead's event ends before the launcher is reached

    def test_both_exact_forms_of_a_role_pass_and_a_loose_match_does_not(self):
        marker = self.root / ".git" / "aidd" / turn_budget.FOLDER
        for i, event in enumerate(
            (
                '{"hook_event_name":"PostToolUse","cwd":"%s","agent_id":"c1","agent_type":"aidd-team:developer"}',
                '{"hook_event_name":"PostToolUse","cwd":"%s","agent_id":"c2","agent_type": "aidd-developer"}',
            )
        ):
            self.assertEqual(self.run_hook(event % self.root).returncode, 0)
            self.assertTrue((marker / f"c{i + 1}.n").exists(), event)
        loose = json.dumps({"cwd": str(self.root), "agent_id": "c3", "agent_type": "x", "note": "aidd-"}, separators=(",", ":"))
        self.assertEqual(self.run_hook(loose).stdout, "")
        self.assertFalse((marker / "c3.n").exists())

    @unittest.skipUnless(os.path.exists("/bin/sh") and os.path.exists("/bin/cat"), "needs /bin/sh and /bin/cat")
    def test_an_event_with_many_agent_type_keys_is_checked_in_linear_time(self):
        """A looser pattern took 4.5 s for 20,000 keys under macOS's sh, and the hook's timeout at about 30,000."""
        event = '{"cwd":"x","a":[' + ",".join(['{"agent_type":"Explore"}'] * 20000) + "]}"
        start = time.perf_counter()
        done = subprocess.run(["/bin/sh", "-c", hook_gate.POST_TOOL_GATE + "false"], input=event, capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0)
        self.assertLess(time.perf_counter() - start, 1.0)

    def test_the_check_unsets_a_printf_function_it_would_otherwise_call(self):
        self.assertTrue(hook_gate.POST_TOOL_GATE.startswith("unset -f printf"))

    def test_the_check_is_posix_sh_with_no_eval(self):
        gate = hook_gate.POST_TOOL_GATE
        for word in ("eval", "source", "bash", "[["):
            self.assertNotIn(word, gate)
        self.assertEqual(subprocess.run(["/bin/sh", "-n", "-c", gate + "true"]).returncode, 0)


class HandoffHoldTests(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        make_repo(root, "team")

    def stop(self, **extra) -> dict:
        event = {
            "hook_event_name": "SubagentStop",
            "session_id": "s1",
            "cwd": str(self.root),
            "agent_id": "a1",
            "agent_type": ROLE,
            "agent_transcript_path": "/tmp/a.jsonl",
            "stop_hook_active": False,
            "last_assistant_message": "I changed the code and the tests pass.",
            **extra,
        }
        out, err = io.StringIO(), io.StringIO()
        self.assertEqual(session_hooks.run_session_hook("stop", io.StringIO(json.dumps(event)), out, err), 0, err.getvalue())
        return json.loads(out.getvalue()) if out.getvalue() else {}

    def test_a_role_that_stops_with_no_handoff_note_is_held_once(self):
        for agent in ("aidd-team:developer", "aidd-team:reviewer", "aidd-architect"):
            answer = self.stop(agent_type=agent)
            self.assertEqual(answer["decision"], "block", agent)
            self.assertIn(HOLD, answer["reason"])
        self.assertEqual(self.stop(stop_hook_active=True), {})

    def test_a_handoff_block_lets_it_stop(self):
        self.assertEqual(self.stop(last_assistant_message=HANDOFF), {})
        self.assertEqual(self.stop(last_assistant_message="Done.\n\n~~~aidd-handoff\ndone: x\n~~~"), {})

    def test_a_note_written_earlier_in_the_run_counts(self):
        path = self.root / "agent.jsonl"
        note = "Done.\n```aidd-handoff\ndone: x\n```"
        path.write_text(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": note}]}}) + "\n", encoding="utf-8")
        self.assertEqual(self.stop(agent_transcript_path=str(path), last_assistant_message="All done."), {})
        # A note in a file the role wrote (the Spec) counts too; one only a tool result shows, or none, does not.
        path.write_text(
            json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit", "input": {"new_string": note}}]}}) + "\n",
            encoding="utf-8",
        )
        self.assertEqual(self.stop(agent_transcript_path=str(path), last_assistant_message="All done."), {})
        path.write_text(json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "content": note}]}}) + "\n", encoding="utf-8")
        self.assertEqual(self.stop(agent_transcript_path=str(path), last_assistant_message="All done.")["decision"], "block")
        self.assertEqual(self.stop(agent_transcript_path=str(self.root / "missing.jsonl"), last_assistant_message="All done.")["decision"], "block")

    def test_a_line_shaped_like_a_live_transcript_line_counts(self):
        """A live transcript line (Claude Code 2.1.x) opens with `parentUuid`, `isSidechain`, and `agentId`, so the word
        `assistant` sits far past its first 200 characters; keys only, no text copied from a real run."""
        note = "```aidd-handoff\ndone: x\n```"
        shape = {
            "parentUuid": "p" * 36,
            "isSidechain": True,
            "agentId": "a" * 17,
            "userType": "external",
            "cwd": "/x" * 40,
            "sessionId": "s" * 36,
            "version": "2.1.312",
            "gitBranch": "feature",
            "message": {"id": "m", "type": "message", "role": "assistant", "model": "m", "content": [{"type": "text", "text": note}], "usage": {}},
            "requestId": "r",
            "type": "assistant",
            "uuid": "u" * 36,
            "timestamp": "2026-10-29T10:00:00.000Z",
        }
        line = json.dumps(shape)
        self.assertGreater(line.index('"assistant"'), 200)
        path = self.root / "agent.jsonl"
        path.write_text('{"type":"user"}\n' + line + "\n", encoding="utf-8")
        self.assertEqual(self.stop(agent_transcript_path=str(path), last_assistant_message="All done."), {})
        shape["type"], shape["message"]["role"] = "user", "user"  # the same text in a user line (a tool result) is no note
        path.write_text(json.dumps(shape) + "\n", encoding="utf-8")
        self.assertEqual(self.stop(agent_transcript_path=str(path), last_assistant_message="All done.")["decision"], "block")

    def entry(self, *blocks: dict, role: str = "assistant") -> str:
        return json.dumps({"type": role, "message": {"role": role, "content": list(blocks)}}, ensure_ascii=False) + "\n"

    def stop_with(self, transcript: str) -> dict:
        path = self.root / "agent.jsonl"
        path.write_text(transcript, encoding="utf-8")
        return self.stop(agent_transcript_path=str(path), last_assistant_message="All done.")

    def test_only_what_a_role_wrote_counts_as_a_note(self):
        note = "```aidd-handoff\ndone: x\n```"
        text, tool = {"type": "text", "text": note}, "tool_use"
        self.assertEqual(self.stop_with(self.entry(text)), {})
        for name, given in (
            ("Write", {"file_path": "a", "content": note}),
            ("Edit", {"new_string": note}),
            ("MultiEdit", {"edits": [{"new_string": note}]}),
            ("write", {"content": note}),
        ):
            self.assertEqual(self.stop_with(self.entry({"type": tool, "name": name, "input": given})), {}, name)
        # Not a note: thinking, a search for the word, another tool's input, a tool's result, a write tool's other fields.
        for block in (
            {"type": "thinking", "thinking": note},
            {"type": tool, "name": "Grep", "input": {"pattern": note}},
            {"type": tool, "name": "Bash", "input": {"command": "echo '" + note + "'"}},
            {"type": tool, "name": "Read", "input": {"file_path": note}},
            {"type": tool, "name": "Edit", "input": {"old_string": note, "new_string": "x"}},
            {"type": "tool_result", "content": note},
        ):
            self.assertEqual(self.stop_with(self.entry(block))["decision"], "block", block)

    def test_a_note_after_a_line_separator_character_is_still_found(self):
        """Only a newline ends a transcript line: U+2028, U+2029, and U+0085 inside a message must not cut it in two."""
        for separator in ("\u2028", "\u2029", "\u0085", "\x0b", "\x0c"):
            text = {"type": "text", "text": f"Done.{separator}\n```aidd-handoff\ndone: x\n```"}
            self.assertEqual(self.stop_with(self.entry(text)), {}, repr(separator))

    def test_the_words_aidd_handoff_in_prose_are_no_note(self):
        self.assertEqual(self.stop(last_assistant_message="I will write the aidd-handoff block later.")["decision"], "block")

    def test_the_lead_and_helpers_are_never_held(self):
        self.assertEqual(self.stop(agent_type="Explore"), {})
        self.assertEqual(self.stop(agent_type="general-purpose"), {})
        self.assertEqual(self.stop(agent_type="reviewer"), {})  # another project's agent with a role's name
        self.assertEqual(self.stop(hook_event_name="Stop", agent_type=None, agent_id=None), {})

    def test_a_message_the_hook_cannot_read_is_not_held(self):
        for message in (None, 5, ["x"]):
            self.assertEqual(self.stop(last_assistant_message=message), {})

    def test_hooks_off_do_not_hold(self):
        cfg = self.root / ".aidd" / "config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + "\nhooks:\n  level: off\n", encoding="utf-8")
        self.assertEqual(self.stop(), {})

    def test_a_repository_that_never_adopted_aidd_is_not_held(self):
        (self.root / ".aidd" / "config.yaml").unlink()
        self.assertEqual(self.stop(), {})

    def test_the_hold_joins_a_stop_reminder_in_one_answer(self):
        answer = self.stop()
        self.assertEqual(answer["reason"].count(HOLD), 1)

    def test_another_harness_s_stop_holds_in_its_own_format(self):
        event = {
            "hook_event_name": "SubagentStop",
            "cwd": str(self.root),
            "agent_type": ROLE,
            "last_assistant_message": "no note",
            "turn_id": "t",
            "session_id": "s",
        }
        out = io.StringIO()
        session_hooks.run_session_hook("stop", io.StringIO(json.dumps(event)), out, io.StringIO())
        self.assertEqual(json.loads(out.getvalue())["decision"], "block")  # Codex reads Claude Code's reply


if __name__ == "__main__":
    unittest.main()
