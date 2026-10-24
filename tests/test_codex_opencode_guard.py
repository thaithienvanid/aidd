"""Codex and OpenCode V2: aidd's guard in each harness's own hook.

Codex reads `.codex/hooks.json` in Claude Code's shape and sends Claude Code's fields plus a `turn_id`; an edit is
`apply_patch`, its patch in `tool_input.command` (as codex 0.156 sends it). OpenCode V2 runs the plugin
`.opencode/plugins/aidd.js`, which sends `harness`, `tool`, `input`, `sessionID`, and `agent` and throws on a deny
(as opencode 2.0.32 and 2.1.0 run it). It reads OpenCode's bus for a finished turn and an ended compaction, and adds the
stop reminder and the compaction note as synthetic messages (opencode 2.1.0). The events below are the ones those
versions sent in a live run.
"""

import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, git, make_repo

from aidd import config
from aidd.docsgen import generate
from aidd.guard import dialects, git_commands, pre_tool, write_targets
from aidd.setup import adoption, codex_wiring, doctor_checks, hook_wiring, opencode_wiring, uninstalling


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
        self.assertEqual((write["tool_name"], write["tool_input"], write["agent_type"]), ("Write", {"file_path": "c.txt", "content": "hi"}, "aidd-reviewer"))
        edit = dialects.OPENCODE.normalize(opencode_event(root, "edit", {"path": "a.py", "oldString": "x", "newString": "y"}))
        self.assertEqual((edit["tool_name"], edit["tool_input"]["old_string"], edit["tool_input"]["new_string"]), ("Edit", "x", "y"))
        patch = dialects.OPENCODE.normalize(opencode_event(root, "apply_patch", {"patchText": add_file_patch("x.py")}, agent="general"))
        self.assertEqual((patch["tool_name"], patch["agent_type"]), (dialects.APPLY_PATCH, "general"))
        server = dialects.OPENCODE.normalize(opencode_event(root, "github_merge_pull_request", {"pullNumber": 1}))
        self.assertEqual(server["tool_name"], "mcp__opencode__github_merge_pull_request")
        read = dialects.OPENCODE.normalize(opencode_event(root, "read", {"path": "README.md"}))
        self.assertNotIn("tool_name", read)
        code = dialects.OPENCODE.normalize(opencode_event(root, "execute", {"code": "x"}))  # each tool it calls is checked too
        self.assertEqual(code["tool_name"], "mcp__opencode__execute")

    def test_opencode_code_mode_is_marked_as_a_tool_the_guard_cannot_read(self):
        """`execute` runs code whose own tool calls never reach the guard: the event names no file and no command the
        guard can check, so the dialect marks it and the guard denies it. Every other tool stays readable."""
        root = Path("/tmp/repo")
        code = dialects.OPENCODE.normalize(opencode_event(root, "execute", {"code": "await tools.write({})"}))
        self.assertTrue(code["opaque_tool"])
        for tool, tool_input in (("read", {"path": "README.md"}), ("shell", {"command": "ls"}), ("write", {"path": "a.txt", "content": "x"})):
            with self.subTest(tool):
                self.assertNotIn("opaque_tool", dialects.OPENCODE.normalize(opencode_event(root, tool, tool_input)))

    def test_opencode_a_shell_call_with_no_command_text_is_marked_never_read_as_empty(self):
        """A shell call whose command is not text names nothing the guard can check, and an empty command would pass."""
        root = Path("/tmp/repo")
        for command in (["gh", "pr", "merge", "1"], {"text": "gh pr merge 1"}, None, 7):
            with self.subTest(command=command):
                event = dialects.OPENCODE.normalize(opencode_event(root, "shell", {"command": command}))
                self.assertEqual((event["tool_name"], event["opaque_tool"]), ("Bash", dialects.OPAQUE_SHELL))


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

    def test_opencode_a_prompt_the_hook_records_comes_back_as_context(self):
        from aidd.guard import session_hooks

        event = {"harness": "opencode", "hook_event_name": "UserPromptSubmit", "prompt": "approve SPEC-220", "sessionID": "ses_1", "cwd": str(self.root)}
        seen = []
        out = io.StringIO()
        session_hooks.prompt_submit(event, out, on_prompt=lambda text, root, session_id: seen.append(text) or "aidd: recorded")
        self.assertEqual(seen, ["approve SPEC-220"])
        self.assertEqual(json.loads(out.getvalue()), {"context": "aidd: recorded"})

    def test_opencode_session_context_is_the_shape_the_plugin_reads_and_the_hint_goes_with_each_prompt(self):
        """The plugin adds `context` from the session-start and the prompt hooks to the person's prompt, so the next-step
        line goes with each prompt, as in the other harnesses."""
        self.assertEqual(dialects.OPENCODE.context("SessionStart", "aidd: hi"), {"context": "aidd: hi"})
        self.assertTrue(dialects.OPENCODE.prompt_hint_due({"harness": "opencode", "hook_event_name": "UserPromptSubmit"}))
        plugin = opencode_wiring.plugin_text()
        self.assertIn("first?.context", plugin)
        self.assertNotIn("additionalContext", plugin)

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

    def test_opencode_code_mode_is_denied_with_the_direct_calls_named(self):
        """A tool the guard cannot read runs the tools it calls itself, so it is denied rather than allowed, and the
        reason names what to use instead."""
        denied = json.loads(guard(opencode_event(self.root, "execute", {"code": "await tools.write({path: 'x'})"})))
        self.assertEqual(denied["decision"], "deny")
        self.assertIn("directly", denied["reason"])
        self.assertIn("write", denied["reason"])

    def test_opencode_a_shell_call_the_guard_cannot_read_is_denied_with_what_to_do(self):
        denied = json.loads(guard(opencode_event(self.root, "shell", {"command": ["gh", "pr", "merge", "1"]})))
        self.assertEqual(denied["decision"], "deny")
        self.assertIn("run it again as one command line", denied["reason"])

    def test_opencode_an_agents_confirmed_approval_is_denied_so_the_terminals_dialog_owns_it(self):
        """The terminal surface records `--decided-via opencode`; the guard denies the same words from an agent's shell,
        in OpenCode as in Claude Code."""
        for command in (
            "aidd approve spec SPEC-220 --confirmed abc1234 --decided-via opencode",
            "aidd land --confirmed abc1234",
            "aidd proposal decide --reason=fits --confirmed go --decided-via opencode -- PROP-1 go",
            f"aidd proposal sign-off --confirmed {'a' * 32} --decided-via opencode -- PROP-1",
        ):
            with self.subTest(command):
                self.assertEqual(json.loads(guard(opencode_event(self.root, "shell", {"command": command})))["decision"], "deny")


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

    def test_codex_init_adds_the_mcp_server_to_the_persons_config_and_uninstall_takes_only_it_back(self):
        """Codex reads a trusted project's `.codex/config.toml`, its `[mcp_servers]` too (codex 0.156 listed the block
        below in `codex mcp list` in a live run). Init appends one block and keeps every other line."""
        import tomllib

        path = self.root / codex_wiring.CONFIG_FILE
        path.parent.mkdir(parents=True)
        mine = 'model = "gpt-6-luna"\n\n[mcp_servers.docs]\ncommand = "docs-mcp"\n'
        path.write_text(mine, encoding="utf-8")
        self.init("codex")
        self.init("codex")  # a second run changes nothing
        text = path.read_text(encoding="utf-8")
        self.assertEqual(text.count("[mcp_servers.aidd]"), 1)
        servers = tomllib.loads(text)["mcp_servers"]
        self.assertEqual(servers["aidd"], {"command": "sh", "args": ["-c", 'exec "$HOME"/.aidd/bin/aidd mcp']})
        self.assertEqual(servers["docs"], {"command": "docs-mcp"})
        uninstalling.uninstall(self.root, yes=True)
        self.assertEqual(path.read_text(encoding="utf-8"), mine)

    def test_codex_keeps_a_config_that_names_its_own_aidd_server_or_is_not_toml(self):
        path = self.root / codex_wiring.CONFIG_FILE
        path.parent.mkdir(parents=True)
        for text in ('[mcp_servers.aidd]\ncommand = "aidd"\nargs = ["mcp"]\n', "this = is = not toml\n"):
            with self.subTest(text=text):
                path.write_text(text, encoding="utf-8")
                actions: list[str] = []
                codex_wiring.install_mcp(self.root, actions)
                self.assertEqual(path.read_text(encoding="utf-8"), text)
                self.assertTrue(actions[-1].startswith("kept"), actions)
        path.unlink()
        self.init("codex")
        uninstalling.uninstall(self.root, yes=True)
        self.assertFalse(path.exists(), "a file that held only aidd's block goes with it")

    def test_codex_flows_are_skills_it_runs_only_when_named(self):
        from aidd.setup import harness_text, team_install

        files = team_install.team_files(["codex"], claude_files=False)
        commands = sorted(p.stem for p in (ROOT / "plugins" / "aidd-team" / "commands").glob("*.md"))
        for flow in commands:
            with self.subTest(flow):
                skill = files[f".agents/skills/aidd-{flow}/SKILL.md"]
                self.assertTrue(skill.startswith(f"---\nname: aidd-{flow}\ndescription: "), skill[:60])
                self.assertIn(f"after `$aidd-{flow}`", skill)
                self.assertEqual(files[f".agents/skills/aidd-{flow}/agents/openai.yaml"], "policy:\n  allow_implicit_invocation: false\n")
                for claude_only in ("${CLAUDE_SESSION_ID}", 'isolation: "worktree"', "Agent call", "with the Skill tool", "/clear"):
                    self.assertNotIn(claude_only, skill)
        self.assertIn(harness_text.lead_block("codex"), files[".agents/skills/aidd-implement/SKILL.md"])
        self.assertIn("aidd's session note names at the start", files[".agents/skills/aidd-autopilot/SKILL.md"])
        # Antigravity reads the same folder: where both are wired, one file names how each starts a role.
        both = team_install.team_files(["codex", "antigravity"], claude_files=False)[".agents/skills/aidd-implement/SKILL.md"]
        self.assertIn("`invoke_subagent` tool in Antigravity, or by asking Codex", both)
        self.assertIn("after `/aidd-implement` in Antigravity, or `$aidd-implement` in Codex", both)

    def test_every_codex_swap_still_matches_its_source(self):
        from aidd import knowledge
        from aidd.setup import harness_text, team_install

        for name, swaps in harness_text.CODEX_COMMANDS.items():
            text = team_install._team_text((ROOT / "plugins" / "aidd-team" / "commands" / name).read_text(encoding="utf-8"))
            for old, _ in swaps:
                with self.subTest(command=name, text=old[:40]):
                    self.assertIn(old, text)
        for old in harness_text.CODEX_LEAD:
            with self.subTest(lead=old[:40]):
                self.assertTrue(any(old in rule for rule in knowledge.roles()["loop"]["lead"]))

    def test_upgrade_tells_a_codex_team_from_an_antigravity_one_by_the_files_only_one_gets(self):
        from aidd.setup import team_install

        own = team_install.harness_paths()
        self.assertNotIn(".agents/skills/aidd-implement/SKILL.md", own["codex"] | own["antigravity"])
        self.assertIn(".agents/skills/aidd-implement/agents/openai.yaml", own["codex"])
        self.assertIn(".agents/agents/aidd-developer.md", own["antigravity"])

    def test_opencode_init_writes_the_plugin_and_uninstall_removes_it(self):
        self.init("opencode")
        for rel, text in opencode_wiring.files().items():
            with self.subTest(rel):
                self.assertEqual((self.root / rel).read_text(encoding="utf-8"), text)
        self.assertNotIn("__FAIL_CLOSED_PROFILES__", opencode_wiring.plugin_text())
        self.assertEqual(opencode_wiring.state(self.root), "current")
        report = "\n".join(message for _, message in doctor_checks.doctor(self.root))
        self.assertIn("OpenCode V2: the guard plugin is in", report)
        uninstalling.uninstall(self.root, yes=True)
        for rel in opencode_wiring.files():
            with self.subTest(rel):
                self.assertFalse((self.root / rel).exists())

    def test_opencode_state_and_doctor_read_the_terminal_half_too(self):
        """The plugin and its terminal half are one install: a missing or stale half means the guard files are gone or
        an older aidd's, and doctor names what is wrong."""
        self.init("opencode")
        self.assertTrue((self.root / opencode_wiring.PLUGIN_FILE).is_file())
        tui = self.root / opencode_wiring.TUI_FILE
        self.assertTrue(tui.is_file())
        tui.write_text("// an older aidd's terminal half\n", encoding="utf-8")
        self.assertEqual(opencode_wiring.state(self.root), "stale")
        report = "\n".join(message for _, message in doctor_checks.doctor(self.root))
        self.assertIn(opencode_wiring.TUI_DIR, report)
        tui.unlink()
        # aidd's plugin with a file gone is still an older aidd's: `aidd upgrade` writes them all, never leaving the old guard.
        self.assertEqual(opencode_wiring.state(self.root), "stale")
        self.assertIn(opencode_wiring.TUI_DIR, "\n".join(message for _, message in doctor_checks.doctor(self.root)))
        (self.root / opencode_wiring.PLUGIN_FILE).unlink()
        self.assertEqual(opencode_wiring.state(self.root), "missing")

    def test_windows_gets_a_launcher_the_plugin_can_start(self):
        """On Windows the user launcher is `aidd.cmd`, a batch file beside the sh script, and the plugin starts it
        through `cmd.exe`. `aidd init` writes it wherever the machine is Windows."""
        argv = ["C:\\Python\\python.exe", "-I", "-m", "aidd"]
        text = hook_wiring.windows_launcher_script(argv)
        self.assertIn('"C:\\Python\\python.exe"', text)
        self.assertIn("-m aidd", text)
        self.assertIn("%*", text)
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            old = hook_wiring.user_launcher_path
            hook_wiring.user_launcher_path = lambda: home / "aidd.cmd"
            self.addCleanup(setattr, hook_wiring, "user_launcher_path", old)
            launcher = hook_wiring.launcher()
            hook_wiring.install_user_launcher(self.root, launcher, [], windows=True)
            self.assertEqual((home / "aidd.cmd").read_text(encoding="utf-8"), hook_wiring.windows_launcher_script(launcher[0]))

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

# The stand-in launcher: it records every hook it is asked for, and answers each as aidd's own hook would. `aidd hook
# pre-tool` writes a deny only while `$HOME/deny` is there, so one launcher serves the allow and the deny case.
RECORDER = (
    'hook="$2"\n'
    "input=$(cat)\n"
    'printf \'%s\\n\' "$hook" >> "$HOME/calls.txt"\n'
    'printf \'{"hook": "%s", "event": %s}\\n\' "$hook" "$input" >> "$HOME/events.jsonl"\n'
    'case "$hook" in\n'
    '  session-start) echo \'{"context": "aidd: the loop is at step 2"}\' ;;\n'
    '  prompt-submit) echo \'{"context": "aidd: recorded"}\' ;;\n'
    '  pre-tool) if [ -f "$HOME/deny" ]; then echo \'{"decision": "deny", "reason": "aidd: no"}\'; fi ;;\n'
    # aidd hook stop, as session_hooks.stop answers OpenCode: nothing once a stop continued the agent, a block at level
    # strict, else context.
    '  stop) case "$input" in *\'"stop_hook_active":true\'*) ;; *) if [ -f "$HOME/strict" ]; then '
    'echo \'{"decision": "block", "reason": "aidd: run the tests"}\'; else echo \'{"context": "aidd: run the tests"}\'; fi ;; esac ;;\n'
    "esac\n"
)
DENY = 'cat >/dev/null; echo \'{"decision": "deny", "reason": "aidd: no"}\'\n'

# The stand-in OpenCode: a context with the parts the plugin uses, driven by config.json. Every hook it registers is
# kept, then asked in the order the scenario names.
DRIVER = """
import { existsSync, readFileSync } from "node:fs"
import { join } from "node:path"
import { pathToFileURL } from "node:url"
const cfg = JSON.parse(readFileSync(process.argv[2], "utf8"))
const out = { prompts: [], synthetic: [] }
const callCount = () => {
  const path = join(process.env.HOME, "calls.txt")
  return existsSync(path) ? readFileSync(path, "utf8").split("\\n").filter(Boolean).length : 0
}
// The bus, as opencode 2.1.0 hands it to a plugin: `event.subscribe()` is an async iterable of { id, type, data }.
let release = () => {}
let go = () => {}
const busDone = new Promise((done) => { release = done })
const scenarioDone = new Promise((done) => { go = done })
async function* bus() {
  await scenarioDone // the bus speaks after the scenario's prompts and compaction, in the order a session makes them
  for (const step of cfg.events ?? []) {
    yield { id: "evt_1", created: 0, type: step.type, durable: true, data: step.data }
    await new Promise((next) => setTimeout(next, 50))
  }
  release()
}
let toolHook = null
const sessionHooks = {}
const shellHooks = {}
const memory = new Map(Object.entries(cfg.storage ?? {}))
const ctx = {
  location: { directory: cfg.project },
  tool: { hook: async (name, fn) => { out.toolHook = name; toolHook = fn } },
  shell: { hook: async (name, fn) => { shellHooks[name] = fn } },
  session: {
    hook: async (name, fn) => { sessionHooks[name] = fn },
    get: async () => {
      if (cfg.sessionError) throw new Error("no record")
      return { id: "ses_1", parentID: cfg.parent ?? undefined, location: cfg.location ? { directory: cfg.location } : undefined }
    },
    synthetic: async (input) => { out.synthetic.push(input) },
  },
  storage: { get: async (key) => memory.get(key), set: async (key, value) => { memory.set(key, value) } },
}
if (cfg.events) ctx.event = { subscribe: () => bus() }
const mod = await import(pathToFileURL(process.argv[3]).href)
await mod.default.setup(ctx)
if (cfg.invocation) out.invocation = typeof mod.launcherInvocation === "function" ? mod.launcherInvocation(cfg.invocation.platform, cfg.invocation.launcher) : null
if (cfg.shell) {
  if (typeof shellHooks["create.before"] !== "function") out.shell = "no create.before hook"
  else {
    try {
      await shellHooks["create.before"]({ command: cfg.shell, cwd: cfg.project, timeout: 1000, shell: "/bin/sh", env: {} })
      out.shell = "ran"
    } catch (e) { out.shell = "blocked: " + e.message }
  }
}
// The bash tool as opencode 2.1.0 runs it: `execute.before` with the session, then Shell.create's `create.before` with only
// { command, cwd, timeout, shell, env }. A step `{ tool }` is the tool call (of `session`, else ses_1), and `{ shell }` the shell it creates (null:
// the command the tool call ran), `later` ms after. Its `env` is one an agent could set.
const realNow = Date.now
let clock = 0
Date.now = () => realNow() + clock
out.steps = []
for (const step of cfg.steps ?? []) {
  if ("tool" in step) {
    const event = { tool: "bash", input: { command: step.tool, description: "run" }, sessionID: step.session ?? "ses_1", agent: "build", callID: "call_1" }
    try { await toolHook(event); out.ran = event.input.command; out.steps.push("ran") } catch (e) { out.steps.push("blocked: " + e.message) }
    continue
  }
  clock += step.later ?? 0
  const command = step.shell ?? out.ran
  try {
    await shellHooks["create.before"]({ command, cwd: cfg.project, timeout: 120000, shell: "/bin/zsh", env: step.env ?? { TERM: "xterm-256color", OPENCODE_TERMINAL: "1" } })
    out.steps.push("ran")
  } catch (e) { out.steps.push("blocked: " + e.message) }
}
if (cfg.command !== null && cfg.command !== undefined) {
  try {
    const event = { tool: "shell", input: { command: cfg.command }, sessionID: "ses_1", agent: "build" }
    await toolHook(event)
    out.ran = event.input.command
  } catch (e) { out.blocked = e.message }
}
for (const text of cfg.prompts ?? []) {
  const event = { sessionID: "ses_1", prompt: { text } }
  if (typeof sessionHooks["prompt"] === "function") await sessionHooks["prompt"](event)
  out.prompts.push(event.prompt.text)
}
if (cfg.compact) {
  if (typeof sessionHooks["compaction"] === "function") {
    // The compaction hook's input, as opencode 2.1.0 sent it in a live run.
    await sessionHooks["compaction"]({ sessionID: "ses_1", model: {}, system: [], messages: [], options: {}, agent: "build", tools: {} })
    out.compacted = true
  } else out.compacted = "no compaction hook"
}
for (const text of cfg.promptsAfter ?? []) {
  const event = { sessionID: "ses_1", prompt: { text } }
  await sessionHooks["prompt"](event)
  out.prompts.push(event.prompt.text)
}
go()
if (cfg.events) {
  await busDone
  // The bus's handlers run on their own: wait until the hooks they start have answered.
  for (let waited = 0; waited < 20000 && (out.synthetic.length < cfg.synthetic || callCount() < cfg.calls); waited += 50) {
    await new Promise((next) => setTimeout(next, 50))
  }
  await new Promise((next) => setTimeout(next, 200))
}
out.storage = Object.fromEntries(memory)
console.log(JSON.stringify(out))
"""


@unittest.skipUnless(NODE, "node runs the plugin")
class PluginTests(unittest.TestCase):
    """The plugin itself, run by node with a stand-in launcher and a stand-in OpenCode context."""

    def run_plugin(
        self,
        launcher_body: str = RECORDER,
        *,
        config_text: str = "",
        subfolder: str = "",
        location: str | None = None,
        location_config: str = "",
        session_error: bool = False,
        parent: str | None = None,
        prompts: list[str] | None = None,
        command: str | None = None,
        shell: str | None = None,
        compact: bool = False,
        deny: bool = False,
        storage: dict | None = None,
        invocation: dict | None = None,
        prompts_after: list[str] | None = None,
        events: list[tuple[str, dict]] | None = None,
        strict: bool = False,
        wait: tuple[int, int] = (0, 0),
        steps: list[dict] | None = None,
    ) -> dict:
        """Run the plugin under node and return what the scenario produced. `location` is the folder the session works
        in, when it is not the folder the plugin was loaded in; `shell` is a shell OpenCode creates outside the tool
        flow; `invocation` asks the plugin's Windows/POSIX launcher choice instead of running it. `events` are the bus's
        (type, data), sent after the prompts, the compaction, and `prompts_after`; `wait` is the (launcher calls,
        synthetic messages) the bus's handlers make, which the driver waits for. `strict` makes the stop hook block.
        `steps` are bash tool calls and the shells they create, in order, as DRIVER reads them."""
        tmp = Path(tempfile.mkdtemp())
        self.tmp = tmp
        self.addCleanup(shutil.rmtree, tmp, True)
        home = tmp / "home"
        launcher = home / ".aidd" / "bin" / "aidd"
        launcher.parent.mkdir(parents=True)
        launcher.write_text("#!/bin/sh\n" + launcher_body, encoding="utf-8")
        launcher.chmod(0o755)
        if deny:
            (home / "deny").write_text("1", encoding="utf-8")
        if strict:
            (home / "strict").write_text("1", encoding="utf-8")
        project = tmp / "project"
        (project / ".aidd").mkdir(parents=True)
        (project / subfolder).mkdir(parents=True, exist_ok=True)
        if config_text:
            (project / ".aidd" / "config.yaml").write_text(config_text, encoding="utf-8")
        where = project / subfolder
        if location:
            where = tmp / location
            (where / ".aidd").mkdir(parents=True, exist_ok=True)
            if location_config:
                (where / ".aidd" / "config.yaml").write_text(location_config, encoding="utf-8")
        (tmp / "aidd.mjs").write_text(opencode_wiring.plugin_text(), encoding="utf-8")
        (tmp / "config.json").write_text(
            json.dumps(
                {
                    "project": str(project / subfolder),
                    "location": str(where) if location else None,
                    "parent": parent,
                    "sessionError": session_error,
                    "prompts": prompts or [],
                    "command": command,
                    "shell": shell,
                    "compact": compact,
                    "storage": storage or {},
                    "invocation": invocation,
                    "promptsAfter": prompts_after or [],
                    "events": [{"type": t, "data": d} for t, d in events] if events is not None else None,
                    "calls": wait[0],
                    "synthetic": wait[1],
                    "steps": steps or [],
                }
            ),
            encoding="utf-8",
        )
        (tmp / "driver.mjs").write_text(DRIVER, encoding="utf-8")
        r = subprocess.run(
            [str(NODE), str(tmp / "driver.mjs"), str(tmp / "config.json"), str(tmp / "aidd.mjs")],
            capture_output=True,
            text=True,
            env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
            timeout=60,
        )
        self.stderr = r.stderr
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])

    def calls(self) -> list[str]:
        """Every hook the plugin asked the launcher for, in order."""
        path = self.tmp / "home" / "calls.txt"
        return path.read_text(encoding="utf-8").split() if path.exists() else []

    def events(self) -> list[dict]:
        path = self.tmp / "home" / "events.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def sent(self, hook: str) -> dict:
        """The event the plugin sent for `hook`."""
        matches = [record["event"] for record in self.events() if record["hook"] == hook]
        self.assertTrue(matches, f"no {hook} event, only {self.calls()}")
        return matches[-1]

    def test_a_root_sessions_prompt_goes_to_the_prompt_hook_and_its_note_joins_it(self):
        out = self.run_plugin(prompts=["approve SPEC-1"], command="ls")
        self.assertEqual(out["prompts"], ["approve SPEC-1\n\naidd: the loop is at step 2\n\naidd: recorded"])
        sent = self.sent("prompt-submit")
        self.assertEqual((sent["hook_event_name"], sent["prompt"], sent["harness"]), ("UserPromptSubmit", "approve SPEC-1", "opencode"))
        self.assertEqual(self.sent("pre-tool")["input"]["command"], "ls")

    def test_a_subagents_prompt_is_never_the_persons(self):
        out = self.run_plugin(prompts=["approve SPEC-1"], parent="ses_0")
        self.assertEqual(out["prompts"], ["approve SPEC-1"])
        self.assertEqual(self.calls(), [])

    def test_a_deny_blocks_with_the_reason_and_no_answer_runs_the_tool(self):
        self.assertEqual(self.run_plugin(DENY, command="ls")["blocked"], "aidd: no")
        self.assertEqual(self.run_plugin(command="ls")["ran"], "ls")

    def test_a_shell_opencode_creates_is_asked_of_the_guard_and_a_deny_stops_it(self):
        """A command block or a terminal shell skips the tool hook; `create.before` asks the guard before it runs."""
        out = self.run_plugin(shell="gh pr merge 1")
        self.assertEqual(out["shell"], "ran")
        self.assertEqual((self.sent("pre-tool")["tool"], self.sent("pre-tool")["input"]["command"]), ("shell", "gh pr merge 1"))
        self.assertEqual(self.run_plugin(shell="gh pr merge 1", deny=True)["shell"], "blocked: aidd: no")

    def test_an_argv_shell_reaches_the_guard_as_the_command_that_runs(self):
        """An argv joined with plain spaces reads as another command: `sh -c "git push ..."` would be `sh -c git`."""
        self.run_plugin(shell=["sh", "-c", "git push --force origin main"])
        self.assertEqual(self.sent("pre-tool")["input"]["command"], "sh -c 'git push --force origin main'")
        self.run_plugin(shell=["echo", "it's"])
        self.assertEqual(self.sent("pre-tool")["input"]["command"], "echo 'it'\"'\"'s'")

    def test_a_shell_the_guard_has_no_opinion_on_runs(self):
        self.assertEqual(self.run_plugin(shell="python3 -m unittest")["shell"], "ran")

    def test_the_guard_and_the_prompt_act_in_the_sessions_own_repository(self):
        """A session moved to another folder, or a worktree, is guarded and recorded where it works, not where the
        plugin was loaded."""
        self.run_plugin(location="worktree", command="ls", prompts=["aidd status"])
        for hook in ("pre-tool", "prompt-submit", "session-start"):
            with self.subTest(hook):
                self.assertEqual(self.sent(hook)["cwd"], str(self.tmp / "worktree"))

    def test_an_aidd_that_cannot_run_fails_open_unless_the_sessions_project_fails_closed(self):
        self.assertEqual(self.run_plugin("exit 3\n", command="ls", location="worktree")["ran"], "ls")
        blocked = self.run_plugin("exit 3\n", command="ls", location="worktree", location_config="profile: audited\n")
        self.assertIn("A project that requires the guard blocks each step until then", blocked["blocked"])
        # `mode: enforce` fails closed too, as every other harness's hook and the guard read it (repo_config.fails_closed).
        enforced = self.run_plugin("exit 3\n", command="ls", location="worktree", location_config="profile: team\nmode: enforce  # gate blocks\n")
        self.assertIn("A project that requires the guard blocks each step until then", enforced["blocked"])
        advising = self.run_plugin("exit 3\n", command="ls", location="worktree", location_config="profile: team\nmode: advisory\n")
        self.assertEqual(advising["ran"], "ls")
        # A session in a folder below the project's top still finds the project's config.
        self.assertIn(
            "A project that requires the guard blocks each step until then",
            self.run_plugin("exit 3\n", config_text="profile: audited\n", command="ls", subfolder="src/app")["blocked"],
        )

    def test_a_session_the_plugin_cannot_read_is_not_silent(self):
        out = self.run_plugin(prompts=["approve SPEC-1"], session_error=True)
        self.assertEqual(out["prompts"], ["approve SPEC-1"])
        self.assertIn("could not read this session", self.stderr)
        self.assertEqual(self.calls(), [])

    def test_a_sessions_first_prompt_carries_the_session_note_and_a_compaction_saves_the_state(self):
        out = self.run_plugin(prompts=["one", "two"], compact=True)
        self.assertEqual(self.calls()[:2], ["session-start", "prompt-submit"])
        self.assertEqual(self.calls().count("session-start"), 1)
        self.assertEqual(self.calls().count("prompt-submit"), 2)
        self.assertEqual(self.calls().count("pre-compact"), 1)
        self.assertEqual(out["prompts"][0], "one\n\naidd: the loop is at step 2\n\naidd: recorded")
        self.assertEqual(out["prompts"][1], "two\n\naidd: recorded")
        self.assertTrue(any("started" in key for key in out["storage"]), out["storage"])

    def test_a_shell_command_in_a_shape_the_plugin_cannot_read_never_runs(self):
        """An empty command would pass the guard, so a command that is neither text nor an argv of text is denied, with
        what to do instead, and aidd is never asked."""
        for shell in ({"argv": ["gh", "pr", "merge", "1"]}, ["gh", 1], []):
            with self.subTest(shell=shell):
                self.assertIn("run it again as one command line", self.run_plugin(shell=shell)["shell"])
                self.assertEqual(self.calls(), [])
        for command in (["gh", "pr", "merge", "1"], {"text": "ls"}, 7):
            with self.subTest(command=command):
                self.assertIn("run it again as one command line", self.run_plugin(command=command)["blocked"])
                self.assertEqual(self.calls(), [])

    # A turn as opencode 2.1.0 sent it on the bus in a live run: `session.execution.started`, then
    # `session.execution.succeeded`, each with `data.sessionID` only.
    TURN = [("session.execution.started", {"sessionID": "ses_1"}), ("session.execution.succeeded", {"sessionID": "ses_1"})]

    def test_a_finished_turn_runs_the_stop_hook_and_its_reminder_waits_for_the_next_turn(self):
        """At the default level the reminder joins the session for the agent's next turn and starts none, as the live
        run showed: OpenCode queued it, and delivered it with the next step."""
        out = self.run_plugin(events=self.TURN, wait=(1, 1))
        sent = self.sent("stop")
        self.assertEqual((sent["harness"], sent["hook_event_name"], sent["sessionID"], sent["stop_hook_active"]), ("opencode", "Stop", "ses_1", False))
        self.assertEqual(out["synthetic"], [{"sessionID": "ses_1", "text": "aidd: run the tests", "description": "aidd", "resume": False}])
        self.assertEqual(dialects.of(sent).key, "opencode")
        self.assertEqual(dialects.of(sent).normalize(sent)["session_id"], "ses_1")

    def test_at_level_strict_a_stop_continues_the_agent_once(self):
        """A block starts one more turn; that turn's stop says a stop hook already continued the agent, as Claude Code's
        `stop_hook_active` does, so it never loops. The person's next prompt clears it."""
        out = self.run_plugin(events=self.TURN * 2, strict=True, wait=(2, 1))
        self.assertEqual(out["synthetic"], [{"sessionID": "ses_1", "text": "aidd: run the tests", "description": "aidd", "resume": True}])
        stops = [r["event"]["stop_hook_active"] for r in self.events() if r["hook"] == "stop"]
        self.assertEqual(stops, [False, True])
        self.assertTrue(out["storage"]["aidd:stop-continued:ses_1"])
        cleared = self.run_plugin(prompts=["go on"], storage={"aidd:stop-continued:ses_1": True})
        self.assertFalse(cleared["storage"]["aidd:stop-continued:ses_1"])

    def test_one_turn_runs_one_stop_check_and_a_subagents_turn_none(self):
        self.run_plugin(events=[*self.TURN, ("session.idle", {"sessionID": "ses_1"})], wait=(1, 1))
        self.assertEqual(self.calls(), ["stop"])
        self.run_plugin(events=[("session.idle", {"sessionID": "ses_1"})])  # an end with no turn begun
        self.assertEqual(self.calls(), [])
        out = self.run_plugin(events=self.TURN, parent="ses_0")
        self.assertEqual((self.calls(), out["synthetic"]), ([], []))

    def test_after_a_compaction_the_session_start_note_reads_the_state_back_at_once(self):
        """OpenCode goes on working after a compaction with no prompt, so when `session.compaction.ended` comes, the
        session-start hook runs with source `compact` and its note joins the session, as Claude Code's does."""
        ended = {"sessionID": "ses_1", "reason": "manual", "model": {"id": "m", "providerID": "p"}, "text": "## Objective"}
        out = self.run_plugin(prompts=["one"], compact=True, events=[("session.compaction.ended", ended)], wait=(4, 1))
        self.assertEqual(self.calls(), ["session-start", "prompt-submit", "pre-compact", "session-start"])
        self.assertEqual([r["event"]["source"] for r in self.events() if r["hook"] == "session-start"], ["startup", "compact"])
        self.assertEqual(out["synthetic"], [{"sessionID": "ses_1", "text": "aidd: the loop is at step 2", "description": "aidd", "resume": False}])
        self.assertFalse(out["storage"]["aidd:compacted:ses_1"])

    def test_without_the_bus_the_next_prompt_carries_the_compaction_note(self):
        out = self.run_plugin(prompts=["one"], compact=True, prompts_after=["two"])
        self.assertEqual(self.calls(), ["session-start", "prompt-submit", "pre-compact", "session-start", "prompt-submit"])
        self.assertEqual([r["event"]["source"] for r in self.events() if r["hook"] == "session-start"], ["startup", "compact"])
        self.assertEqual(out["prompts"][1], "two\n\naidd: the loop is at step 2\n\naidd: recorded")
        self.assertFalse(out["storage"]["aidd:compacted:ses_1"])

    def test_windows_starts_the_launcher_aidd_init_writes_there(self):
        launcher = "/home/me/.aidd/bin/aidd"
        win = self.run_plugin(invocation={"platform": "win32", "launcher": launcher})
        self.assertEqual(win["invocation"], {"file": "cmd.exe", "args": ["/c", launcher + ".cmd"]})
        posix = self.run_plugin(invocation={"platform": "darwin", "launcher": launcher})
        self.assertEqual(posix["invocation"], {"file": launcher, "args": []})

    def test_the_session_word_becomes_the_sessions_id_before_the_guard_reads_it(self):
        ran = self.run_plugin(command="aidd autopilot stop --session ${AIDD_SESSION_ID}")
        self.assertEqual(ran["ran"], "aidd autopilot stop --session ses_1")
        sent = self.sent("pre-tool")
        self.assertEqual((sent["input"]["command"], sent["sessionID"]), ("aidd autopilot stop --session ses_1", "ses_1"))
        self.assertEqual(dialects.of(sent).normalize(sent)["session_id"], "ses_1")

    START = "aidd autopilot start --work SPEC-1 --session ${AIDD_SESSION_ID}"
    STARTED = "aidd autopilot start --work SPEC-1 --session ses_1"

    def shell_sent(self) -> dict:
        """The last event the plugin sent the guard for a shell OpenCode created."""
        shells = [r["event"] for r in self.events() if r["hook"] == "pre-tool" and r["event"]["tool"] == "shell"]
        self.assertTrue(shells, f"no shell event, only {self.calls()}")
        return shells[-1]

    def test_the_bash_tools_own_shell_names_the_session_of_the_call_the_guard_allowed(self):
        """OpenCode 2.1.0's create.before names no session, so a live run's `aidd autopilot start --session` was denied
        there. The shell takes the session and agent of the tool call with the same text, so the guard allows it."""
        out = self.run_plugin(steps=[{"tool": self.START}, {"shell": None, "later": 300}])
        self.assertEqual(out["steps"], ["ran", "ran"])
        sent = self.shell_sent()
        self.assertEqual((sent["input"]["command"], sent["sessionID"], sent["agent"]), (self.STARTED, "ses_1", "build"))
        self.assertIsNone(git_commands.autopilot_session_denial(self.STARTED, dialects.of(sent).normalize(sent)))

    def test_any_other_shell_names_no_session_and_never_one_an_agent_sets(self):
        """A shell with other text, one past the window, a second shell with the same text, the shell after a denied call
        or a call the guard could not answer, and a shell two sessions wait on with the same text name no session, so
        the guard denies the start as before. The env an agent could set is never read."""
        agent_env = {"OPENCODE_SESSION_ID": "ses_1", "AIDD_SESSION_ID": "ses_1"}
        fails_once = 'if [ ! -f "$HOME/once" ]; then : > "$HOME/once"; cat >/dev/null; exit 3; fi\n' + RECORDER
        cases = {
            "other text": ([{"tool": "ls"}, {"shell": self.STARTED, "env": agent_env}], RECORDER, False),
            "too late": ([{"tool": self.START}, {"shell": None, "later": 11000}], RECORDER, False),
            "used once": ([{"tool": self.START}, {"shell": None}, {"shell": None}], RECORDER, False),
            "denied call": ([{"tool": self.START}, {"shell": self.STARTED}], RECORDER, True),
            "no answer": ([{"tool": self.START}, {"shell": self.STARTED}], fails_once, False),
            "two sessions": ([{"tool": self.STARTED}, {"tool": self.STARTED, "session": "ses_2"}, {"shell": self.STARTED}], RECORDER, False),
        }
        for name, (steps, launcher, deny) in cases.items():
            with self.subTest(name):
                self.run_plugin(launcher, steps=steps, deny=deny)
                sent = self.shell_sent()
                self.assertEqual(sent["input"]["command"], self.STARTED)
                self.assertNotIn("sessionID", sent)
                why = git_commands.autopilot_session_denial(self.STARTED, dialects.of(sent).normalize(sent)) or ""
                self.assertIn("the hook event names no session", why)
                self.assertIn("`${AIDD_SESSION_ID}` in OpenCode", why)


if __name__ == "__main__":
    unittest.main()
