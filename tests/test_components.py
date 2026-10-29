"""`components`: each part of aidd runs unless the config turns it off, turns off alone, and is silent when off."""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT, make_repo, run_cli

from aidd import config
from aidd.guard import approval_commands, decision_files, pre_tool, repo_config, session_hooks
from aidd.kernel import git as gitmod
from aidd.setup import antigravity_wiring, doctor_checks, grok_wiring, hook_wiring


def git(*args: str) -> str:
    return gitmod.run(list(args)).strip()


def load(extra: str = "", parent: str | None = None) -> config.Config:
    text = 'aidd_version: "1.0.0"\nprofile: "team"\nowners: {approvers: ["@x"]}\n' + ("extends: [{path: parent.yaml}]\n" if parent else "") + extra
    return config.load_text(text, read=lambda rel: parent if rel == "parent.yaml" else None)


class SwitchTests(unittest.TestCase):
    def test_every_part_is_on_unless_turned_off(self):
        for name in config.COMPONENTS:
            self.assertTrue(config.component_on({}, name), name)
            self.assertFalse(config.component_on({"components": {name: False}}, name), name)

    def test_autopilot_runs_the_loop_so_it_stops_with_it(self):
        self.assertFalse(config.component_on({"components": {"spec_steps": False}}, "autopilot"))
        self.assertTrue(config.component_on({"components": {"autopilot": False}}, "spec_steps"))

    def test_the_config_names_only_known_parts(self):
        self.assertNotIn("guard", config.COMPONENTS)  # the guard follows the loop
        for extra in ("components: {guard: false}\n", "components: {team: false}\n"):
            with self.subTest(extra=extra), self.assertRaises((config.ConfigError, ValueError)) as raised:
                load(extra)
        self.assertNotIn("components.spec_steps", str(raised.exception))
        with self.assertRaises((config.ConfigError, ValueError)) as raised:
            load("components: {guard: false}\n")
        self.assertIn("unknown field 'guard'", str(raised.exception))
        self.assertNotIn("hooks", config.COMPONENTS)  # the session hooks are `hooks.level`
        for old in ("components: {hooks: false}\n", "hooks: {session_start: false}\n"):
            with self.subTest(old=old), self.assertRaisesRegex(config.ConfigError, r"unknown field"):
                load(old)

    def test_an_agent_cannot_turn_the_session_hooks_off(self):
        base = 'aidd_version: "1.0.0"\nprofile: team\n'
        said = decision_files.config_loosening(config.CONFIG_PATH, base, base + 'hooks: {level: "off"}\n')
        self.assertEqual(said, "it sets `hooks.level` to off, which silences the session hooks")
        self.assertIsNone(decision_files.config_loosening(config.CONFIG_PATH, base, base + "hooks: {level: strict}\n"))

    def test_a_parent_that_turns_a_part_on_binds_its_children(self):
        parent = 'aidd_version: "1.0.0"\nprofile: "team"\ncomponents: {spec_steps: true}\n'
        cfg = load("components: {spec_steps: false, autopilot: false}\n", parent)
        self.assertTrue(config.component_on(cfg.raw, "spec_steps"))
        self.assertFalse(config.component_on(cfg.raw, "autopilot"))
        self.assertTrue(any("components.spec_steps=false ignored" in w for w in cfg.warnings), cfg.warnings)


class RepoTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_repo(Path(tmp.name).resolve() / "repo", "team")

    def turn_off(self, *names: str) -> None:
        path = self.root / config.CONFIG_PATH
        hooks = 'hooks:\n  level: "off"\n' if "hooks" in names else ""  # the session hooks' switch is their level
        parts = "".join(f"  {n}: false\n" for n in names if n != "hooks")
        path.write_text(path.read_text(encoding="utf-8") + hooks + ("components:\n" + parts if parts else ""), encoding="utf-8")

    def guard(self, rel: str) -> str:
        out = io.StringIO()
        event = {"tool_name": "Write", "cwd": str(self.root), "tool_input": {"file_path": str(self.root / rel), "content": "x"}}
        pre_tool.pre_tool_hook(io.StringIO(json.dumps(event)), out)
        return out.getvalue()

    def session_start(self) -> str:
        out = io.StringIO()
        event = {"hook_event_name": "SessionStart", "source": "startup", "cwd": str(self.root)}
        session_hooks.run_session_hook("session-start", io.StringIO(json.dumps(event)), out, io.StringIO())
        return out.getvalue()

    def command(self, text: str) -> str:
        out = io.StringIO()
        event = {"tool_name": "Bash", "cwd": str(self.root), "tool_input": {"command": text}}
        pre_tool.pre_tool_hook(io.StringIO(json.dumps(event)), out)
        return out.getvalue()

    def test_with_the_loop_off_every_edit_goes_but_the_rules_on_deciding_stay(self):
        self.assertIn('"deny"', self.guard(".github/workflows/ci.yml"))
        self.turn_off("spec_steps")
        self.assertEqual(self.guard(".github/workflows/ci.yml"), "")  # no Spec, no scope, no role area
        for text in ("aidd approve merge", "aidd land", "gh pr merge 1", "git push --force origin main"):
            self.assertIn('"deny"', self.command(text), text)
        # Loosening who must approve stays a person's, loop or not.
        out = io.StringIO()
        cfg = self.root / config.CONFIG_PATH
        looser = re.sub(r"(?m)^profile:.*$", "profile: solo", cfg.read_text(encoding="utf-8"))
        event = {"tool_name": "Write", "cwd": str(self.root), "tool_input": {"file_path": str(cfg), "content": looser}}
        pre_tool.pre_tool_hook(io.StringIO(json.dumps(event)), out)
        self.assertIn("loosens who must approve", out.getvalue())

    def test_a_dialog_answer_counts_only_from_where_a_person_answered(self):
        with contextlib.chdir(self.root):
            head = git("rev-parse", "HEAD")
            code, out = run_cli("approve", "merge", "--confirmed", head, "--decided-via", "mcp:ide")
        self.assertNotEqual(code, 0)
        self.assertIn("counts only from aidd's MCP server", out)
        with contextlib.chdir(self.root):
            code, out = run_cli("approve", "merge", "--confirmed", head, "--decided-via", "prompt")
        self.assertNotEqual(code, 0)
        self.assertIn("counts only from aidd's own prompt hook", out)

    def test_fail_closed_blocks_only_in_an_aidd_repository(self):
        with mock.patch.dict(os.environ, {approval_commands.FAIL_CLOSED_ENV: "1"}), mock.patch.object(pre_tool, "_pre_tool", side_effect=RuntimeError):
            self.assertIn('"deny"', self.guard("src/app.py"))
            with tempfile.TemporaryDirectory() as other:
                out = io.StringIO()
                event = {"tool_name": "Write", "cwd": other, "tool_input": {"file_path": f"{other}/x.txt", "content": "x"}}
                pre_tool.pre_tool_hook(io.StringIO(json.dumps(event)), out)
                self.assertEqual(out.getvalue(), "", "a project without aidd is never blocked by it")

    def test_the_audited_profile_and_enforce_mode_fail_closed_with_no_variable_and_the_others_do_not(self):
        env = {k: v for k, v in os.environ.items() if k != approval_commands.FAIL_CLOSED_ENV}
        path = self.root / config.CONFIG_PATH
        before = path.read_text(encoding="utf-8")
        self.addCleanup(path.write_text, before, encoding="utf-8")
        self.assertRegex(before, r"(?m)^mode: enforce")  # make_repo enforces
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(pre_tool, "_pre_tool", side_effect=RuntimeError):
            self.assertIn('"deny"', self.guard("src/app.py"))  # `mode: enforce` fails closed under any profile
            self.assertTrue(repo_config.fails_closed(str(self.root)))
            before = re.sub(r"(?m)^mode: .*$", "mode: advisory", before)
            path.write_text(before, encoding="utf-8")
            self.assertEqual(self.guard("src/app.py"), "")  # an advising team profile does not fail closed
            self.assertFalse(repo_config.fails_closed(str(self.root)))
            path.write_text(re.sub(r"(?m)^profile: .*$", 'profile: "audited"  # finance', before), encoding="utf-8")
            self.assertTrue(repo_config.fails_closed(str(self.root)))
            out = self.guard("src/app.py")
            self.assertIn('"deny"', out)
            self.assertIn("audited profile", out)
            self.assertIn("audited profile", approval_commands.forbidden_action("echo 'unbalanced", str(self.root)) or "")
            self.assertFalse(repo_config.fails_closed(tempfile.gettempdir()))  # never outside a repository that uses aidd

    def test_the_fail_closed_profiles_are_those_whose_mode_enforces(self):
        """A config only tightens its profile, so a profile whose mode enforces always does: its guard fails closed."""
        profiles = json.loads((ROOT / "schemas" / "profiles.json").read_text(encoding="utf-8"))["profiles"]
        self.assertEqual(set(config.FAIL_CLOSED_PROFILES), {name for name, p in profiles.items() if p.get("mode") in config.FAIL_CLOSED_MODES})

    def test_every_shell_fallback_matches_the_fail_closed_profiles_with_builtins_only(self):
        pre_tool_hook = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        self.assertIn(hook_wiring.fail_closed_test('"$C"'), pre_tool_hook)  # the plugin's launcher, on the config it found
        self.assertIn(hook_wiring.fail_closed_test(".aidd/config.yaml"), grok_wiring.hook_command("pre-tool"))  # its own folder
        self.assertIn(hook_wiring.fail_closed_test("../.aidd/config.yaml"), antigravity_wiring.hook_command("pre-tool"))  # it runs from .agents/
        keys = [*(f"profile:{p}" for p in config.FAIL_CLOSED_PROFILES), *(f"mode:{m}" for m in config.FAIL_CLOSED_MODES)]
        self.assertIn(f"case $k:$v in {'|'.join(keys)}) f=1", hook_wiring.fail_closed_test())
        with tempfile.TemporaryDirectory() as d:
            Path(d, ".aidd").mkdir()
            planted = Path(d, "bin")
            planted.mkdir()
            Path(planted, "grep").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")  # a program the repository planted
            Path(planted, "grep").chmod(0o755)
            cases = {
                "profile: audited\n": 2,
                "profile: 'audited' # regulated\n": 2,
                "profile: audited\r\nowners: {}\r\n": 2,  # CRLF
                "profile: team\nprofile: audited\n": 2,  # every profile line, as the Python reads them
                "profile: team\n": 1,
                "profile: audited-lite\n": 1,
                "profile: team\r\n": 1,
                # `mode: enforce` fails closed too, under any profile; a nested `mode` key or another mode does not.
                "profile: team\nmode: enforce\n": 2,
                "mode: 'enforce'  # the gate blocks\r\n": 2,
                "profile: solo\nmode: advisory\n": 1,
                "hooks:\n  mode: enforce\n": 1,
                "mode: enforced\n": 1,
            }
            env0 = {k: v for k, v in os.environ.items() if k != approval_commands.FAIL_CLOSED_ENV}
            for text, code in cases.items():
                Path(d, ".aidd", "config.yaml").write_bytes(f"aidd_version: 1\n{text}".encode())
                env = {"PATH": str(planted), "CLAUDE_PROJECT_DIR": d}
                run = subprocess.run(["/bin/sh", "-c", f"{hook_wiring.fail_closed_test()} && exit 2; exit 1"], cwd="/", env=env, capture_output=True)
                self.assertEqual((run.returncode, run.stderr), (code, b""), text)
                with mock.patch.dict(os.environ, env0, clear=True):
                    self.assertEqual(repo_config.fails_closed(d), code == 2, f"the Python and the shell agree: {text!r}")
            missing = {"PATH": str(planted), "CLAUDE_PROJECT_DIR": str(Path(d, "nowhere"))}
            run = subprocess.run(["/bin/sh", "-c", f"{hook_wiring.fail_closed_test()} && exit 2; exit 1"], env=missing, capture_output=True)
            self.assertEqual((run.returncode, run.stderr), (1, b""), "no config: no opinion, and no error")

    def test_doctor_warns_when_fail_closed_reaches_every_project(self):
        with tempfile.TemporaryDirectory() as home:
            Path(home, "settings.json").write_text(json.dumps({"env": {"AIDD_HOOK_FAIL_CLOSED": "1"}}), encoding="utf-8")
            with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": home}):
                warned = doctor_checks.fail_closed_scope(self.root)
        self.assertEqual([level for level, _ in warned], ["warn"])
        self.assertIn("reaches every project", warned[0][1])

    def test_the_hooks_or_the_loop_off_silence_the_session_hooks_but_the_loop_off_is_said(self):
        self.assertIn("aidd", self.session_start())
        for part in ("hooks", "spec_steps"):
            with self.subTest(part=part):
                path = self.root / config.CONFIG_PATH
                before = path.read_text(encoding="utf-8")
                self.turn_off(part)
                said = self.session_start()
                if part == "spec_steps":  # only that it is off, and since when, so nobody forgets it
                    self.assertEqual(said.count("aidd:"), 1, said)
                    self.assertIn("the Spec steps are off here (`components.spec_steps: false` in .aidd/config.yaml, in an edit not yet committed)", said)
                    git("-C", str(self.root), "commit", "-qam", "loop off")
                    self.assertRegex(self.session_start(), r"since \d{4}-\d{2}-\d{2}")
                else:
                    self.assertEqual(said, "")
                if part == "hooks":
                    self.assertIn('"deny"', self.guard(".github/workflows/ci.yml"), "the guard keeps working with the hooks off")
                path.write_text(before, encoding="utf-8")

    def test_autopilot_off_refuses_and_says_which_switch(self):
        self.turn_off("spec_steps")
        with contextlib.chdir(self.root):
            code, out = run_cli("autopilot", "next", "--session", "s1")
        self.assertNotEqual(code, 0)
        self.assertIn("autopilot is off here: components.spec_steps is false", out)

    def test_doctor_shows_each_part_and_warns_when_the_gate_still_wants_a_spec(self):
        lines = doctor_checks.component_lines(load('mode: "enforce"\n'))
        self.assertEqual(
            lines, [("ok", "components: hooks balanced, spec_steps on, autopilot on; the guard and the gate block what the rules forbid (mode: enforce)")]
        )
        lines = doctor_checks.component_lines(load('mode: "enforce"\ncomponents: {spec_steps: false}\n'))
        self.assertIn("spec_steps off, autopilot off", lines[0][1])
        self.assertEqual([level for level, _ in lines], ["ok", "info", "warn"])
        lines = doctor_checks.component_lines(load('mode: "advisory"\ncomponents: {spec_steps: false}\n'))
        self.assertEqual([level for level, _ in lines], ["ok", "info"])
        self.assertIn("the Spec steps are off here", lines[1][1])  # said each time, so nobody forgets it
        self.assertIn("advise, and block only a decision an agent makes for a person (mode: advisory)", lines[0][1])


if __name__ == "__main__":
    unittest.main()
