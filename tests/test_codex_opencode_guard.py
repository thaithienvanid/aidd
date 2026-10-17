"""Codex and OpenCode V2: aidd's guard in each harness's own hook.

Codex reads `.codex/hooks.json` in Claude Code's shape and sends Claude Code's fields plus a `turn_id`; an edit is
`apply_patch`, its patch in `tool_input.command` (as codex 0.156 sends it). OpenCode V2 runs the plugin
`.opencode/plugins/aidd.js`, which sends `harness`, `tool`, `input`, `sessionID`, and `agent` and throws on a deny (as
opencode 2.0.26 runs it). The events below are the ones those versions sent in a live run.
"""

import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import git, make_repo

from aidd import config
from aidd.docsgen import generate
from aidd.guard import dialects, pre_tool, write_targets
from aidd.setup import adoption, codex_wiring, doctor_checks, opencode_wiring, uninstalling


def codex_event(root: Path, tool: str, command: str) -> dict:
    return {
        "session_id": "01a149e0-ad7c-7a93-a4bc-e04727333b07",
        "turn_id": "01a149e0-ae2e-7513-afd1-7faa84f5b7cb",
        "transcript_path": "/Users/x/.codex/sessions/2026/10/17/rollout.jsonl",
        "cwd": str(root),
        "hook_event_name": "PreToolUse",
        "model": "gpt-5.6-luna",
        "permission_mode": "default",
        "tool_name": tool,
        "tool_input": {"command": command},
        "tool_use_id": "exec-1",
    }


def opencode_event(root: Path, tool: str, tool_input: dict, agent: str = "build") -> dict:
    return {"harness": "opencode", "hook_event_name": "PreToolUse", "tool": tool, "input": tool_input, "sessionID": "ses_1", "agent": agent, "cwd": str(root)}


def guard(event: dict) -> str:
    out = io.StringIO()
    if pre_tool.pre_tool_hook(io.StringIO(json.dumps(event)), out) != 0:
        raise AssertionError("the guard exited non-zero")
    return out.getvalue()


def add_file_patch(path: str) -> str:
    return f"*** Begin Patch\n*** Add File: {path}\n+hello\n*** End Patch"


class DialectTests(unittest.TestCase):
    def test_codex_events_are_claude_code_shaped_and_claimed_by_turn_or_transcript(self):
        event = codex_event(Path("/tmp/repo"), "Bash", "ls")
        self.assertEqual(dialects.of(event).key, "codex")
        start = {"session_id": "s", "transcript_path": "/Users/x/.codex/sessions/r.jsonl", "cwd": "/tmp/repo", "hook_event_name": "SessionStart"}
        self.assertEqual(dialects.of(start).key, "codex")
        claude = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": "/tmp/repo"}
        self.assertEqual(dialects.of(claude).key, "claude-code")

    def test_a_codex_command_given_as_words_reads_as_its_script(self):
        event = codex_event(Path("/tmp/repo"), "Bash", "")
        event["tool_input"] = {"command": ["bash", "-lc", "git push origin main"]}
        self.assertEqual(dialects.of(event).normalize(event)["tool_input"]["command"], "git push origin main")
        # Another program's `-c` is its own code, never a shell script: the guard reads the whole line.
        event["tool_input"] = {"command": ["python3", "-c", "print(1)"]}
        self.assertEqual(dialects.of(event).normalize(event)["tool_input"]["command"], "python3 -c 'print(1)'")

    def test_a_patch_names_each_file_it_writes(self):
        patch = "*** Begin Patch\n*** Update File: a.py\n*** Move to: b.py\n@@\n-x\n+y\n*** Add File: c.py\n+z\n*** Delete File: d.py\n*** End Patch"
        self.assertEqual(write_targets.apply_patch_targets(patch), ["a.py", "b.py", "c.py", "d.py"])

    def test_opencode_tools_and_agents_map_onto_the_guard(self):
        root = Path("/tmp/repo")
        shell = dialects.of(opencode_event(root, "shell", {"command": "ls"})).normalize(opencode_event(root, "shell", {"command": "ls"}))
        self.assertEqual((shell["tool_name"], shell["tool_input"], shell["session_id"]), ("Bash", {"command": "ls"}, "ses_1"))
        self.assertNotIn("agent_type", shell)
        write = dialects.OPENCODE.normalize(opencode_event(root, "write", {"path": "c.txt", "content": "hi"}, agent="aidd-reviewer"))
        self.assertEqual((write["tool_name"], write["tool_input"], write["agent_type"]), ("Edit", {"file_path": "c.txt"}, "aidd-reviewer"))
        patch = dialects.OPENCODE.normalize(opencode_event(root, "apply_patch", {"patchText": add_file_patch("x.py")}, agent="general"))
        self.assertEqual((patch["tool_name"], patch["agent_type"]), (dialects.APPLY_PATCH, "general"))
        server = dialects.OPENCODE.normalize(opencode_event(root, "github_merge_pull_request", {"pullNumber": 1}))
        self.assertEqual(server["tool_name"], "mcp__opencode__github_merge_pull_request")
        read = dialects.OPENCODE.normalize(opencode_event(root, "read", {"path": "README.md"}))
        self.assertNotIn("tool_name", read)
        code = dialects.OPENCODE.normalize(opencode_event(root, "execute", {"code": "x"}))  # each tool it calls is checked too
        self.assertEqual(code["tool_name"], "mcp__opencode__execute")


class GuardTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_repo(Path(tmp.name).resolve() / "repo", "solo", approvers=["email:me@example.com"], spec="02-normal-feature:specs/SPEC-220.md")

    def test_codex_a_merge_and_a_patch_into_the_git_directory_are_denied(self):
        merge = json.loads(guard(codex_event(self.root, "Bash", "gh pr merge 1")))
        self.assertEqual(merge["hookSpecificOutput"]["permissionDecision"], "deny")
        into_git = guard(codex_event(self.root, dialects.APPLY_PATCH, add_file_patch(str(self.root / ".git" / "refs" / "aidd" / "approvals"))))
        self.assertEqual(json.loads(into_git)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_codex_a_patch_is_read_as_leniently_as_codex_reads_it(self):
        padded = f"*** Begin Patch\n  ***  Add File :  {self.root / '.git' / 'hooks' / 'post-commit'}\n+x\n*** End Patch"
        self.assertEqual(json.loads(guard(codex_event(self.root, dialects.APPLY_PATCH, padded)))["hookSpecificOutput"]["permissionDecision"], "deny")
        unread = json.loads(guard(codex_event(self.root, dialects.APPLY_PATCH, "*** Begin Patch\n*** Frobnicate: x\n*** End Patch")))
        self.assertEqual(unread["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("cannot read which files", unread["hookSpecificOutput"]["permissionDecisionReason"])
        # A header behind Unicode whitespace is read as Codex reads it; one the check cannot read denies the patch.
        nbsp = f"*** Begin Patch\n *** Add File: {self.root / '.git' / 'config'}\n+x\n*** End Patch"
        self.assertEqual(json.loads(guard(codex_event(self.root, dialects.APPLY_PATCH, nbsp)))["hookSpecificOutput"]["permissionDecision"], "deny")
        hidden = f"*** Begin Patch\n*** Add File: notes.txt\n+x\n***Add​File: {self.root / '.git' / 'config'}\n+x\n*** End Patch"
        self.assertIsNone(write_targets.apply_patch_targets(hidden))
        # Codex splits a patch on newlines alone: a line separator inside a header could name another file there.
        self.assertIsNone(write_targets.apply_patch_targets("*** Begin Patch\n*** Add File: tests/a.py x\n+x\n*** End Patch"))
        self.assertEqual(write_targets.apply_patch_targets("*** Begin Patch\r\n*** Add File: a.py\r\n+x\r\n*** End Patch\r\n"), ["a.py"])
        self.assertEqual(write_targets.apply_patch_targets("*** Begin Patch\n*** Add File: a.py\n+x\n*** End of File\n*** End Patch"), ["a.py"])

    def test_codex_a_patch_run_from_the_shell_is_read_as_a_patch(self):
        into_git = f"apply_patch <<'EOF'\n*** Begin Patch\n*** Add File: {self.root / '.git' / 'config'}\n+x\n*** End Patch\nEOF"
        self.assertEqual(json.loads(guard(codex_event(self.root, "Bash", into_git)))["hookSpecificOutput"]["permissionDecision"], "deny")
        unread = json.loads(guard(codex_event(self.root, "Bash", "apply_patch < change.patch")))
        self.assertIn("cannot read which files", unread["hookSpecificOutput"]["permissionDecisionReason"])
        plain = "apply_patch <<'EOF'\n*** Begin Patch\n*** Add File: notes.txt\n+x\n*** End Patch\nEOF"
        self.assertEqual(guard(codex_event(self.root, "Bash", plain)), "")

    def test_an_empty_patch_is_denied(self):
        self.assertEqual(json.loads(guard(codex_event(self.root, dialects.APPLY_PATCH, "")))["hookSpecificOutput"]["permissionDecision"], "deny")
        other_key = opencode_event(self.root, "apply_patch", {"patch": add_file_patch(str(self.root / ".git" / "config"))})
        self.assertEqual(json.loads(guard(other_key))["decision"], "deny")

    def test_codex_a_harmless_command_is_no_opinion(self):
        self.assertEqual(guard(codex_event(self.root, "Bash", "python3 -m unittest")), "")

    def test_opencode_a_reviewer_write_and_a_merge_are_denied_and_a_read_passes(self):
        reviewer = json.loads(guard(opencode_event(self.root, "edit", {"path": "src/app.py", "oldString": "a", "newString": "b"}, agent="aidd-reviewer")))
        self.assertEqual(reviewer["decision"], "deny")
        self.assertTrue(reviewer["reason"].startswith("aidd: "))
        merge = json.loads(guard(opencode_event(self.root, "shell", {"command": "gh pr merge 1"})))
        self.assertEqual(merge["decision"], "deny")
        self.assertEqual(guard(opencode_event(self.root, "read", {"path": "README.md"})), "")
        self.assertEqual(guard(opencode_event(self.root, "shell", {"command": "python3 -m unittest"})), "")


class WiringTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        git(self.root, "init", "-q")

    def init(self, harness: str) -> list[str]:
        chosen = adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=[harness], approvers=["email:me@example.com"])
        return adoption.init(self.root, chosen)

    def test_codex_init_keeps_the_persons_hooks_and_uninstall_removes_only_aidds(self):
        mine = {"type": "command", "command": "echo mine"}
        path = self.root / codex_wiring.HOOKS_FILE
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [mine]}]}}), encoding="utf-8")
        self.init("codex")
        self.init("codex")  # a second run changes nothing
        hooks = json.loads(path.read_text(encoding="utf-8"))["hooks"]
        self.assertEqual(hooks["PreToolUse"][0], {"matcher": "Bash", "hooks": [mine]})
        self.assertEqual(len(hooks["PreToolUse"]), 2)
        self.assertEqual(set(codex_wiring.wired(self.root)), set(codex_wiring.EVENTS))
        report = "\n".join(message for _, message in doctor_checks.doctor(self.root))
        self.assertIn("Codex: the guard hook and the session hooks", report)
        uninstalling.uninstall(self.root, yes=True)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [mine]}]}})

    def test_opencode_init_writes_the_plugin_and_uninstall_removes_it(self):
        self.init("opencode")
        path = self.root / opencode_wiring.PLUGIN_FILE
        self.assertEqual(path.read_text(encoding="utf-8"), opencode_wiring.plugin_text())
        self.assertNotIn("__FAIL_CLOSED_PROFILES__", opencode_wiring.plugin_text())
        self.assertEqual(opencode_wiring.state(self.root), "current")
        report = "\n".join(message for _, message in doctor_checks.doctor(self.root))
        self.assertIn("OpenCode V2: the guard plugin is in", report)
        uninstalling.uninstall(self.root, yes=True)
        self.assertFalse(path.exists())

    def test_codex_fails_closed_from_a_subfolder_of_the_project(self):
        """Codex runs a hook from the session's folder: where aidd cannot start, the fallback finds the project's config above it."""
        (self.root / ".aidd").mkdir()
        (self.root / ".aidd" / "config.yaml").write_text("profile: audited\n", encoding="utf-8")
        below = self.root / "src" / "app"
        below.mkdir(parents=True)
        env = {"HOME": str(self.root / "no-home"), "PATH": "/usr/bin:/bin"}
        r = subprocess.run(["/bin/sh", "-c", codex_wiring.hook_command("pre-tool")], cwd=below, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "deny", r.stderr)
        (self.root / ".aidd" / "config.yaml").write_text("profile: solo\n", encoding="utf-8")
        r = subprocess.run(["/bin/sh", "-c", codex_wiring.hook_command("pre-tool")], cwd=below, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(r.stdout, "", r.stderr)

    def test_the_docs_name_every_guarded_harness(self):
        self.assertTrue(config.HARNESSES["codex"].guard and config.HARNESSES["opencode"].guard)
        self.assertEqual(generate.inline_list("guard-harnesses"), "Claude Code, Codex, Google Antigravity, Grok Build, and OpenCode V2")


def _node() -> str | None:
    """node's own program (a version manager's shim needs the person's HOME, which the plugin runs without)."""
    if not shutil.which("node"):
        return None
    r = subprocess.run(["node", "-p", "process.execPath"], capture_output=True, text=True, timeout=30)
    return r.stdout.strip() or None if r.returncode == 0 else None


NODE = _node()


@unittest.skipUnless(NODE, "node runs the plugin")
class PluginTests(unittest.TestCase):
    """The plugin itself, run by node with a stand-in launcher and a stand-in OpenCode context."""

    def run_plugin(self, launcher_body: str, config_text: str = "", command: str = "ls", subfolder: str = "") -> dict:
        tmp = Path(tempfile.mkdtemp())
        self.tmp = tmp
        self.addCleanup(shutil.rmtree, tmp, True)
        launcher = tmp / "home" / ".aidd" / "bin" / "aidd"
        launcher.parent.mkdir(parents=True)
        launcher.write_text("#!/bin/sh\n" + launcher_body, encoding="utf-8")
        launcher.chmod(0o755)
        (tmp / "project" / ".aidd").mkdir(parents=True)
        (tmp / "project" / subfolder).mkdir(parents=True, exist_ok=True)
        if config_text:
            (tmp / "project" / ".aidd" / "config.yaml").write_text(config_text, encoding="utf-8")
        (tmp / "aidd.mjs").write_text(opencode_wiring.plugin_text(), encoding="utf-8")
        driver = tmp / "driver.mjs"
        driver.write_text(
            "import plugin from './aidd.mjs'\n"
            "let hook\n"
            f"await plugin.setup({{ location: {{ directory: {json.dumps(str(tmp / 'project' / subfolder))} }}, tool: {{ hook: async (name, fn) => {{ hook = fn }} }} }})\n"
            f"const event = {{ tool: 'shell', input: {{ command: {json.dumps(command)} }}, sessionID: 'ses_1', agent: 'build' }}\n"
            "try { await hook(event); console.log(JSON.stringify({ ran: event.input.command })) }\n"
            "catch (e) { console.log(JSON.stringify({ blocked: e.message })) }\n",
            encoding="utf-8",
        )
        r = subprocess.run([str(NODE), str(driver)], capture_output=True, text=True, env={"HOME": str(tmp / "home"), "PATH": "/usr/bin:/bin"}, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_a_deny_blocks_with_the_reason_and_no_answer_runs_the_tool(self):
        deny = 'cat >/dev/null; echo \'{"decision": "deny", "reason": "aidd: no"}\'\n'
        self.assertEqual(self.run_plugin(deny), {"blocked": "aidd: no"})
        self.assertEqual(self.run_plugin("cat >/dev/null\n"), {"ran": "ls"})

    def test_an_aidd_that_cannot_run_fails_open_unless_the_project_fails_closed(self):
        self.assertEqual(self.run_plugin("exit 3\n"), {"ran": "ls"})
        blocked = self.run_plugin("exit 3\n", "profile: audited\n")
        self.assertIn("this project requires it", blocked["blocked"])
        # A session in a folder below the project's top still finds the project's config.
        below = self.run_plugin("exit 3\n", "profile: audited\n", subfolder="src/app")
        self.assertIn("this project requires it", below["blocked"])

    def test_the_session_word_becomes_the_sessions_id_before_the_guard_reads_it(self):
        ran = self.run_plugin('cat > "$HOME/event.json"\n', command="aidd autopilot stop --session ${AIDD_SESSION_ID}")
        self.assertEqual(ran, {"ran": "aidd autopilot stop --session ses_1"})
        sent = json.loads((self.tmp / "home" / "event.json").read_text(encoding="utf-8"))
        self.assertEqual((sent["input"]["command"], sent["sessionID"]), ("aidd autopilot stop --session ses_1", "ses_1"))
        self.assertEqual(dialects.of(sent).normalize(sent)["session_id"], "ses_1")


if __name__ == "__main__":
    unittest.main()
