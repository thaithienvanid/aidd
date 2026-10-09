"""The session hooks (`aidd hook session-start`, `stop`, `pre-compact`), their `[hooks]` config, their wiring, and the
guard's denial log with `aidd metrics --guard`.

Every hook reads the event JSON Claude Code sends on stdin and answers in the documented JSON
(code.claude.com/docs/en/hooks): SessionStart and a Stop reminder through `hookSpecificOutput.additionalContext`,
a strict Stop through top-level `decision` = "block" with a `reason`. It never answers outside a repository that
adopted aidd, never continues an agent a stop hook already continued, and allows on its own failure.
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT, RepoTemplateCase, aidd_subprocess, git, make_repo, run_cli

from aidd import config as cfgmod
from aidd import guard, hooks, metrics, nextstep, repo

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


def call(hook: str, event: dict | str) -> tuple[int, str, str]:
    """Run one hook in this process, as Claude Code would: the event as JSON on stdin."""
    out, err = io.StringIO(), io.StringIO()
    code = hooks.run(hook, io.StringIO(event if isinstance(event, str) else json.dumps(event)), out, err)
    return code, out.getvalue(), err.getvalue()


def load(profile: str, extra: str = "", parent: str | None = None) -> cfgmod.Config:
    text = f'aidd_version = "1.0.0"\nprofile = "{profile}"\n' + ('extends = [{ path = "parent.toml" }]\n' if parent else "") + extra
    return cfgmod.load_text(text, read=lambda rel: parent if rel == "parent.toml" else None)


class LevelConfigTests(unittest.TestCase):
    def test_each_profile_starts_at_its_level(self):
        self.assertEqual(cfgmod.HOOK_LEVEL_DEFAULTS, {"solo": "minimal", "team": "balanced", "org": "balanced", "regulated": "strict"})
        for profile, level in cfgmod.HOOK_LEVEL_DEFAULTS.items():
            self.assertEqual(hooks.level(load(profile)), level, profile)
        self.assertEqual(set(cfgmod.HOOK_LEVEL_DEFAULTS), set(cfgmod.resources.profiles()["order"]))

    def test_a_repository_sets_its_own_level(self):
        self.assertEqual(hooks.level(load("solo", '[hooks]\nlevel = "strict"\n')), "strict")
        self.assertEqual(hooks.level(load("team", '[hooks]\nlevel = "minimal"\n')), "minimal")

    def test_the_schema_rejects_an_unknown_level_or_key(self):
        with self.assertRaises(cfgmod.ConfigError):
            load("team", '[hooks]\nlevel = "paranoid"\n')
        with self.assertRaises(cfgmod.ConfigError):
            load("team", "[hooks]\nsomething = true\n")

    def test_a_child_cannot_lower_the_parents_level(self):
        parent = 'aidd_version = "1.0.0"\nprofile = "team"\n[hooks]\nlevel = "strict"\n'
        cfg = load("team", '[hooks]\nlevel = "minimal"\n', parent)
        self.assertEqual(hooks.level(cfg), "strict")
        self.assertTrue(any("hooks.level='minimal' ignored" in w for w in cfg.warnings), cfg.warnings)
        self.assertEqual(hooks.level(load("team", "", parent)), "strict")  # inherited when the child is silent

    def test_the_parents_profile_default_is_a_floor_too(self):
        parent = 'aidd_version = "1.0.0"\nprofile = "regulated"\n'
        cfg = load("regulated", '[hooks]\nlevel = "balanced"\n', parent)
        self.assertEqual(hooks.level(cfg), "strict")
        self.assertTrue(cfg.warnings)

    def test_the_pre_release_level_name_is_refused(self):
        # 1.0.0 is the first release: "standard", the middle level's name before it, is no alias.
        with self.assertRaises(cfgmod.ConfigError) as err:
            load("team", '[hooks]\nlevel = "standard"\n')
        self.assertIn('$.hooks.level: must be one of minimal, balanced, strict; got "standard"', str(err.exception))

    def test_a_child_may_raise_the_level_and_keeps_its_own_profile_default(self):
        parent = 'aidd_version = "1.0.0"\nprofile = "solo"\n[hooks]\nlevel = "minimal"\n'
        self.assertEqual(hooks.level(load("team", "", parent)), "balanced")  # never below the child's own profile
        self.assertEqual(hooks.level(load("solo", '[hooks]\nlevel = "strict"\n', parent)), "strict")

    def test_a_child_cannot_turn_off_a_hook_the_parent_turns_on(self):
        parent = 'aidd_version = "1.0.0"\nprofile = "team"\n[hooks]\nstop_check = true\n'
        cfg = load("team", "[hooks]\nstop_check = false\nsession_start = false\n", parent)
        self.assertTrue(hooks.enabled(cfg, "stop_check"))
        self.assertFalse(hooks.enabled(cfg, "session_start"))  # the parent left this one to the repository
        self.assertTrue(any("hooks.stop_check=false ignored" in w for w in cfg.warnings), cfg.warnings)

    def test_every_hook_is_on_by_default(self):
        cfg = load("team")
        self.assertTrue(all(hooks.enabled(cfg, s) for s in cfgmod.HOOK_SWITCHES))


class NoConfigTests(unittest.TestCase):
    def test_no_output_outside_an_adopted_repository(self):
        with tempfile.TemporaryDirectory() as d:
            plain = Path(d) / "plain"
            plain.mkdir()
            git(plain, "init", "-q")
            for where in (plain, Path(d), Path(d) / "missing"):
                for hook, name in (("session-start", "SessionStart"), ("stop", "Stop"), ("stop", "SubagentStop"), ("pre-compact", "PreCompact")):
                    self.assertEqual(call(hook, {"hook_event_name": name, "cwd": str(where)}), (0, "", ""), (hook, where))

    def test_bad_input_allows_quietly(self):
        # Without a `cwd` in the event, the hook looks at the directory Claude Code started it in.
        with tempfile.TemporaryDirectory() as d, mock.patch.object(hooks.os, "getcwd", return_value=d):
            for hook in hooks.HANDLERS:
                for text in ("", "not json", "[1, 2]", "null"):
                    code, out, _ = call(hook, text)
                    self.assertEqual((code, out), (0, ""), (hook, text))


class HookCase(RepoTemplateCase):
    """A team repository (level standard) on branch feat, with Spec S-1 (scope src/app/) uncommitted."""

    @classmethod
    def build_template(cls, root):
        make_repo(root, "team")
        (root / "specs" / "S-1.md").write_text(SPEC, encoding="utf-8")

    def set_hooks(self, text: str) -> None:
        config = self.root / ".aidd" / "config.toml"
        current = config.read_text(encoding="utf-8")
        # One [hooks] table: a second one would make the config invalid, which session-start now reports.
        updated = current.replace("\n[hooks]\n", "\n[hooks]\n" + text + "\n", 1) if "\n[hooks]\n" in current else current + "\n[hooks]\n" + text + "\n"
        config.write_text(updated, encoding="utf-8")

    def event(self, name: str, **extra) -> dict:
        base = {"session_id": "abc123", "transcript_path": "/tmp/t.jsonl", "cwd": str(self.root), "permission_mode": "default", "hook_event_name": name}
        return base | extra

    def stop_event(self, **extra) -> dict:
        return self.event("Stop", stop_hook_active=False, last_assistant_message="Done.", background_tasks=[], session_crons=[], **extra)

    def write_code(self, rel: str = "src/app/x.py") -> None:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("print('hi')\n", encoding="utf-8")

    def commit_all(self) -> str:
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "work")
        return git(self.root, "rev-parse", "HEAD").strip()

    def write_evidence(self, head: str, names=("app",), status="passed", folder="aidd-evidence", partial=False) -> Path:
        path = self.root / folder / "evidence.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        results = [{"name": n, "source": "spec", "command": ["true"], "red_green": "green", "status": status, "exit": 0} for n in names]
        data = {"aidd_version": "1.0.0", "head_sha": head, "base_sha": head, "runner": {"ci": "local"}, "results": results}
        if partial:
            data["partial"] = True
        path.write_text(json.dumps(data), encoding="utf-8")
        return path


@unittest.skipUnless(shutil.which("git"), "git is required")
class SessionStartTests(HookCase):
    def test_adds_the_next_steps_as_context(self):
        code, out, err = call("session-start", self.event("SessionStart", source="startup", model="claude-opus-5"))
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(set(payload), {"hookSpecificOutput"})
        self.assertEqual(payload["hookSpecificOutput"]["hookEventName"], "SessionStart")
        context = payload["hookSpecificOutput"]["additionalContext"]
        self.assertIn("S-1", context)
        self.assertIn("feat", context)
        self.assertLessEqual(len(context.splitlines()), hooks.MAX_SUMMARY_LINES)
        self.assertNotIn(hooks.HANDOFF_REMINDER, context)  # only after a compaction

    def test_summary_is_at_most_fifteen_lines(self):
        steps = [nextstep._step(f"step {i}", nextstep.AGENT, "do it") for i in range(20)]
        with mock.patch.object(nextstep, "assess", return_value={"route": None, "steps": steps, "overlaps": []}):
            text = hooks.summary(self.root)
        self.assertLessEqual(len(text.splitlines()), 15)
        self.assertIn("more", text.splitlines()[-1])

    def test_adds_the_route_aidd_assess_shows_for_this_change(self):
        """The loop's entry check, where the agent starts: the route of this change, as `aidd assess` prints it first."""
        self.write_code()
        _, out, _ = call("session-start", self.event("SessionStart", source="startup"))
        lines = json.loads(out)["hookSpecificOutput"]["additionalContext"].splitlines()
        self.assertTrue(lines[0].startswith("aidd assess on branch feat (`aidd list` shows all open work):"), lines[0])
        self.assertRegex(lines[1], r"^Route: (minor|standard|normal|major|emergency) \((fast|spec|emergency) lane\), ")
        self.assertIn("the gate re-checks the real diff", lines[1])
        # A protected path (the gate's own config) makes it major, on the spec lane.
        self.set_hooks('level = "balanced"')
        _, out, _ = call("session-start", self.event("SessionStart", source="startup"))
        self.assertIn("major (spec lane)", json.loads(out)["hookSpecificOutput"]["additionalContext"].splitlines()[1])

    def test_no_route_or_a_failure_leaves_the_route_out(self):
        cfg = hooks._config(str(self.root))
        with mock.patch.object(hooks.rules, "assess_diff", return_value=None):
            # No diff, but the branch's Spec declares its route.
            self.assertIn("set by S-1; the branch has no diff yet", hooks.assessed_lane(str(self.root), cfg) or "")
            (self.root / "specs" / "S-1.md").unlink()
            self.assertIsNone(hooks.assessed_lane(str(self.root), cfg))
        with mock.patch.object(nextstep, "assess", side_effect=RuntimeError("boom")):
            self.assertIsNone(hooks.assessed_lane(str(self.root), cfg))

    def test_the_lane_counts_against_the_fifteen_lines(self):
        steps = [nextstep._step(f"step {i}", nextstep.AGENT, "do it") for i in range(20)]
        with mock.patch.object(nextstep, "assess", return_value={"route": None, "steps": steps, "overlaps": []}):
            text = hooks.summary(self.root, "LANE")
        self.assertLessEqual(len(text.splitlines()), hooks.MAX_SUMMARY_LINES)
        self.assertEqual(text.splitlines()[1], "LANE")
        self.assertIn("more", text.splitlines()[-1])

    def test_after_a_compaction_the_handoff_note_is_added_at_default(self):
        _, out, _ = call("session-start", self.event("SessionStart", source="compact"))
        context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn(hooks.HANDOFF_REMINDER, context)
        self.assertIn("continue from its `stopped_at`", context)  # the handoff key, as the note writes it

    def test_minimal_gives_the_summary_without_the_handoff_note(self):
        self.set_hooks('level = "minimal"')
        _, out, _ = call("session-start", self.event("SessionStart", source="compact"))
        context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("S-1", context)
        self.assertNotIn(hooks.HANDOFF_REMINDER, context)

    def test_each_part_turns_off(self):
        self.set_hooks("session_start = false")
        self.assertEqual(call("session-start", self.event("SessionStart", source="startup")), (0, "", ""))
        _, out, _ = call("session-start", self.event("SessionStart", source="compact"))
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["additionalContext"].count("\n\n"), 0)
        self.set_hooks("compact_note = false")
        self.assertEqual(call("session-start", self.event("SessionStart", source="compact")), (0, "", ""))

    def test_internal_error_allows_with_a_note(self):
        with mock.patch.object(nextstep, "assess", side_effect=KeyError("boom")):
            code, out, err = call("session-start", self.event("SessionStart", source="startup"))
        self.assertEqual((code, out), (0, ""))
        self.assertIn("aidd hook session-start", err)
        self.assertIn("allowing", err)

    def test_through_the_real_entry_point(self):
        run = aidd_subprocess("hook", "session-start", cwd=self.root, input=json.dumps(self.event("SessionStart", source="startup")))
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["hookSpecificOutput"]["hookEventName"], "SessionStart")


@unittest.skipUnless(shutil.which("git"), "git is required")
class StopTests(HookCase):
    def reminder(self, **extra) -> dict:
        code, out, err = call("stop", self.stop_event(**extra))
        self.assertEqual(code, 0, err)
        return json.loads(out) if out else {}

    def test_standard_reminds_without_blocking(self):
        self.write_code()
        payload = self.reminder()
        self.assertNotIn("decision", payload)
        self.assertEqual(payload["hookSpecificOutput"]["hookEventName"], "Stop")
        text = payload["hookSpecificOutput"]["additionalContext"]
        self.assertTrue(text.startswith(hooks.TEST_REMINDER), text)
        self.assertIn("S-1", text)
        self.assertIn("src/app/x.py", text)

    def test_strict_blocks_with_the_reason(self):
        self.set_hooks('level = "strict"')
        self.write_code()
        payload = self.reminder()
        self.assertEqual(payload["decision"], "block")
        self.assertTrue(payload["reason"].startswith(hooks.TEST_REMINDER), payload["reason"])
        self.assertNotIn("hookSpecificOutput", payload)

    def test_minimal_does_nothing(self):
        self.set_hooks('level = "minimal"')
        self.write_code()
        self.assertEqual(self.reminder(), {})

    def test_never_continues_an_agent_a_stop_hook_already_continued(self):
        self.set_hooks('level = "strict"')
        self.write_code()
        self.assertEqual(call("stop", self.stop_event() | {"stop_hook_active": True}), (0, "", ""))
        subagent = self.stop_event() | {"hook_event_name": "SubagentStop", "agent_type": "aidd-team:developer", "stop_hook_active": True}
        self.assertEqual(call("stop", subagent), (0, "", ""))
        self.assertEqual(self.reminder()["decision"], "block")  # the first stop still blocks

    def test_no_active_spec_or_no_change_in_scope_is_quiet(self):
        self.set_hooks('level = "strict"')
        self.assertEqual(self.reminder(), {})  # the Spec alone, no code yet
        self.write_code("docs/notes.md")
        self.assertEqual(self.reminder(), {})  # a change outside every Task's scope
        (self.root / "specs" / "S-1.md").unlink()
        self.write_code()
        self.assertEqual(self.reminder(), {})  # code, but no active Spec

    def test_evidence_on_head_with_every_test_passed_is_quiet(self):
        self.set_hooks('level = "strict"')
        self.write_code()
        head = self.commit_all()
        self.write_evidence(head)
        self.assertEqual(self.reminder(), {})

    def test_evidence_for_another_commit_or_a_failed_test_reminds(self):
        self.set_hooks('level = "strict"')
        self.write_code()
        first = self.commit_all()
        self.write_evidence(first, status="failed")
        self.assertIn("does not record app as passed", self.reminder()["reason"])
        self.write_evidence(first, names=())
        self.assertIn("does not record app as passed", self.reminder()["reason"])
        self.write_evidence(first)
        (self.root / "src/app/y.py").write_text("x = 1\n", encoding="utf-8")
        self.commit_all()
        self.assertIn("another commit", self.reminder()["reason"])

    def test_partial_evidence_is_no_proof(self):
        # `aidd test --changed` writes partial evidence, which the gate never accepts: the stop hook must not either.
        self.set_hooks('level = "strict"')
        self.write_code()
        head = self.commit_all()
        self.write_evidence(head, partial=True)
        self.assertIn("partial", self.reminder()["reason"])
        self.write_evidence(head)
        self.assertEqual(self.reminder(), {})

    def test_the_configured_repository_tests_count_too(self):
        config = self.root / ".aidd" / "config.toml"
        config.write_text(config.read_text(encoding="utf-8") + '\n[[tests]]\nname = "unit"\ncommand = ["true"]\n', encoding="utf-8")
        self.set_hooks('level = "strict"')
        self.write_code()
        head = self.commit_all()
        self.write_evidence(head)
        self.assertIn("unit", self.reminder()["reason"])
        self.write_evidence(head, names=("app", "unit"))
        self.assertEqual(self.reminder(), {})

    def test_the_configured_evidence_folder_counts(self):
        config = self.root / ".aidd" / "config.toml"
        config.write_text(config.read_text(encoding="utf-8") + '\n[evidence]\nartifact = "ci-evidence"\n', encoding="utf-8")
        self.set_hooks('level = "strict"')
        self.write_code()
        head = self.commit_all()
        self.write_evidence(head, folder="ci-evidence")
        self.assertEqual(self.reminder(), {})

    def test_an_edit_after_the_evidence_reminds(self):
        self.set_hooks('level = "strict"')
        self.write_code()
        head = self.commit_all()
        evidence = self.write_evidence(head)
        os.utime(evidence, (1_000_000_000, 1_000_000_000))  # written long before the next edit
        (self.root / "src/app/x.py").write_text("print('changed')\n", encoding="utf-8")
        self.assertIn("changed after", self.reminder()["reason"])

    def test_stop_check_turns_off(self):
        self.set_hooks('level = "strict"\nstop_check = false')
        self.write_code()
        self.assertEqual(self.reminder(), {})

    def test_subagent_stop_counts_only_for_a_role_that_writes_code(self):
        self.write_code()
        base = {"hook_event_name": "SubagentStop", "agent_id": "def456", "agent_transcript_path": "/tmp/a.jsonl"}
        for agent in ("Explore", "general-purpose", "aidd-team:reviewer", "aidd-team:tester", ""):
            self.assertEqual(self.reminder(**base, agent_type=agent), {}, agent)
        for agent in ("aidd-team:developer", "aidd-developer"):
            payload = self.reminder(**base, agent_type=agent)
            self.assertEqual(payload["hookSpecificOutput"]["hookEventName"], "SubagentStop", agent)

    def test_internal_error_allows_even_at_strict(self):
        self.set_hooks('level = "strict"')
        self.write_code()
        with mock.patch.object(hooks, "stop_check", side_effect=RuntimeError("boom")):
            code, out, err = call("stop", self.stop_event())
        self.assertEqual((code, out), (0, ""))
        self.assertIn("aidd hook stop: skipped after an internal error (RuntimeError)", err)

    def test_through_the_real_entry_point(self):
        self.set_hooks('level = "strict"')
        self.write_code()
        run = aidd_subprocess("hook", "stop", cwd=self.root, input=json.dumps(self.stop_event()))
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["decision"], "block")


@unittest.skipUnless(shutil.which("git"), "git is required")
class StopGuardTests(HookCase):
    """At stop, every path the branch changed meets the guard's rules again, so a write the edit hook never saw
    (a plain file write, a script, a build tool) is named before the agent says it is done."""

    def approve(self) -> None:
        # No approvals ref here, so the stored status answers: at ready, Spec approval holds and freezes the tests.
        spec = self.root / "specs" / "S-1.md"
        spec.write_text(SPEC.replace('route = "normal"', 'route = "normal"\nstatus = "ready"'), encoding="utf-8")
        self.write_code("tests/test_app.py")
        self.commit_all()

    def stopped(self, **extra) -> dict:
        code, out, err = call("stop", self.stop_event(**extra))
        self.assertEqual(code, 0, err)
        return json.loads(out) if out else {}

    def test_a_frozen_test_changed_by_a_plain_write_is_named(self):
        self.approve()
        self.assertEqual(self.stopped(), {})  # written before Spec approval, committed with it: nothing to name
        (self.root / "tests" / "test_app.py").write_text("assert True\n", encoding="utf-8")
        text = self.stopped()["hookSpecificOutput"]["additionalContext"]
        self.assertIn("tests/test_app.py", text)
        self.assertIn("frozen by Spec approval", text)

    def test_strict_blocks_once_on_a_forbidden_change(self):
        self.set_hooks('level = "strict"')
        self.approve()
        (self.root / "tests" / "test_app.py").write_text("assert True\n", encoding="utf-8")
        payload = self.stopped()
        self.assertEqual(payload["decision"], "block")
        self.assertIn("tests/test_app.py", payload["reason"])
        self.assertEqual(call("stop", self.stop_event() | {"stop_hook_active": True}), (0, "", ""))

    def test_a_change_outside_the_approved_scope_is_named(self):
        self.approve()
        self.write_code("lib/extra.py")
        text = self.stopped()["hookSpecificOutput"]["additionalContext"]
        self.assertIn("lib/extra.py", text)
        self.assertIn("outside the scope of S-1", text)

    def test_minimal_or_turned_off_names_nothing(self):
        self.approve()
        self.write_code("lib/extra.py")
        for hooks_text in ('level = "minimal"', "stop_check = false"):
            with self.subTest(hooks=hooks_text):
                config = self.root / ".aidd" / "config.toml"
                before = config.read_text(encoding="utf-8")
                self.set_hooks(hooks_text)
                self.assertEqual(self.stopped(), {})
                config.write_text(before, encoding="utf-8")


FAKE_ORCA = """#!{python}
# A stand-in for Orca's `orca` CLI: logs each call as one JSON line, answers `worktree show` with the comment in
# FAKE_ORCA_COMMENT, and fails or hangs when FAKE_ORCA_EXIT or FAKE_ORCA_SLEEP say so.
import json, os, sys, time
with open(os.environ["FAKE_ORCA_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
time.sleep(float(os.environ.get("FAKE_ORCA_SLEEP", "0")))
if os.environ.get("FAKE_ORCA_EXIT"):
    print("Orca is not running", file=sys.stderr)
    sys.exit(int(os.environ["FAKE_ORCA_EXIT"]))
if sys.argv[1:3] == ["worktree", "show"]:
    print(json.dumps({{"id": "1", "ok": True, "result": {{"worktree": {{"path": os.getcwd(), "comment": os.environ.get("FAKE_ORCA_COMMENT", "")}}}}}}))
else:
    print(json.dumps({{"id": "2", "ok": True, "result": {{}}}}))
"""

# What Orca exports into a terminal it manages, in the full-autonomy launch it uses by default.
ORCA_ENV = {"ORCA_PANE_KEY": "tab-1:leaf-1", "ORCA_WORKTREE_ID": "repo-1::/w", "ORCA_AGENT_HOOK_PORT": "49177", "ORCA_AGENT_HOOK_TOKEN": "t"}


@unittest.skipIf(os.name == "nt", "the fake orca CLI is a POSIX script")
@unittest.skipUnless(shutil.which("git"), "git is required")
class OrcaCardTests(HookCase):
    """Inside Orca, session-start and stop put the first step of `aidd assess` on the worktree's card. Display only:
    the hook's output is the same with or without Orca, and every failure is silent."""

    def setUp(self):
        super().setUp()
        bin_dir = Path(self.tmp.name) / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "orca"
        fake.write_text(FAKE_ORCA.format(python=sys.executable), encoding="utf-8")
        fake.chmod(0o755)
        self.log = Path(self.tmp.name) / "orca.log"
        self.path = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"

    def run_hook(self, hook: str, event: dict, orca: bool = True, **env) -> tuple[int, str, str]:
        extra = (ORCA_ENV if orca else {}) | {"PATH": self.path, "FAKE_ORCA_LOG": str(self.log)} | env
        with mock.patch.dict(os.environ, extra):
            return call(hook, event)

    def calls(self) -> list[list[str]]:
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()] if self.log.exists() else []

    def comment_set(self) -> str:
        (args,) = [a for a in self.calls() if a[:2] == ["worktree", "set"]]
        self.assertEqual(args[args.index("--worktree") + 1], f"path:{self.root}")  # this worktree, not the one on screen
        self.assertEqual(args[-1], "--json")
        return args[args.index("--comment") + 1]

    def test_session_start_puts_the_next_step_on_the_card(self):
        start = self.event("SessionStart", source="startup")
        outside = call("session-start", start)
        inside = self.run_hook("session-start", start)
        self.assertEqual(inside, outside)  # the hook's own answer never changes
        self.assertEqual([a[:2] for a in self.calls()], [["worktree", "show"], ["worktree", "set"]])
        comment = self.comment_set()
        self.assertTrue(comment.startswith(hooks.CARD_PREFIX + "S-1 "), comment)
        self.assertEqual(len(comment.splitlines()), 1)
        self.assertLessEqual(len(comment), hooks.MAX_CARD_LINE)

    def test_the_stop_hook_updates_it_and_a_subagent_stop_does_not(self):
        self.assertEqual(self.run_hook("stop", self.stop_event()), call("stop", self.stop_event()))
        self.assertTrue(self.comment_set().startswith(hooks.CARD_PREFIX))
        self.log.unlink()
        self.run_hook("stop", self.event("SubagentStop", stop_hook_active=False, agent_type="Explore"))
        self.assertEqual(self.calls(), [])

    def test_a_persons_lines_on_the_card_stay(self):
        self.run_hook("session-start", self.event("SessionStart", source="startup"), FAKE_ORCA_COMMENT="goal: greet people\naidd: old step (agent)")
        comment = self.comment_set()
        self.assertEqual(comment.splitlines()[0], "goal: greet people")
        self.assertEqual(len(comment.splitlines()), 2)
        self.assertNotIn("old step", comment)
        self.assertEqual(hooks.CARD_PREFIX, "aidd: ")
        self.assertEqual(hooks.merge_comment("", "aidd: x"), "aidd: x")
        self.assertEqual(hooks.merge_comment("aidd: x", "aidd: x"), "aidd: x")
        # Only aidd's own line is replaced: a line that merely starts with "aidd" is someone else's.
        self.assertEqual(hooks.merge_comment("goal: g\naidd next: mine (you)\naidd: old", "aidd: x"), "goal: g\naidd next: mine (you)\naidd: x")
        self.assertFalse(hasattr(hooks, "LEGACY_CARD_PREFIX"))

    def test_an_unchanged_card_is_not_written(self):
        line = hooks.card_line(self.root)
        self.run_hook("session-start", self.event("SessionStart", source="startup"), FAKE_ORCA_COMMENT=line)
        self.assertEqual([a[:2] for a in self.calls()], [["worktree", "show"]])

    def test_nothing_happens_outside_orca_or_when_turned_off(self):
        start = self.event("SessionStart", source="startup")
        self.run_hook("session-start", start, orca=False)
        self.assertEqual(self.calls(), [])
        # Inside Orca, but the CLI Orca names is not there: no fallback to the `orca` on PATH.
        self.assertEqual(self.run_hook("session-start", start, ORCA_CLI_COMMAND="orca-not-installed")[2], "")
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.run_hook("session-start", start, ORCA_CLI_COMMAND="orca")[2], "")
        self.assertEqual(len(self.calls()), 2)
        self.log.unlink()
        self.set_hooks("orca_status = false")
        self.run_hook("session-start", start)
        self.assertEqual(self.calls(), [])

    def test_a_failing_or_hanging_orca_is_silent_and_time_boxed(self):
        start = self.event("SessionStart", source="startup")
        expected = call("session-start", start)
        self.assertEqual(self.run_hook("session-start", start, FAKE_ORCA_EXIT="1"), expected)
        self.assertEqual([a[:2] for a in self.calls()], [["worktree", "show"]])  # a failed read writes nothing
        with mock.patch.object(hooks, "ORCA_TIMEOUT", 0.5):
            began = time.monotonic()
            self.assertEqual(self.run_hook("session-start", start, FAKE_ORCA_SLEEP="10"), expected)
            self.assertLess(time.monotonic() - began, 5)
        with mock.patch.object(hooks, "card_line", side_effect=RuntimeError("boom")):
            self.assertEqual(self.run_hook("session-start", start), expected)  # no stderr note either

    def state(self, comment: str) -> str:
        self.assertEqual(len(comment.splitlines()), 1)
        self.assertLessEqual(len(comment), hooks.MAX_CARD_LINE)
        self.assertTrue(comment.startswith(hooks.CARD_PREFIX), comment)
        return comment.rpartition(hooks.CARD_STATE_SEP)[2]

    def test_the_card_says_working_while_the_agent_has_the_work(self):
        self.run_hook("session-start", self.event("SessionStart", source="startup"))
        self.assertEqual(self.state(self.comment_set()), "working")
        self.log.unlink()
        self.run_hook("stop", self.stop_event())  # HEAD was committed a moment ago: not stuck
        self.assertEqual(self.state(self.comment_set()), "working")

    def test_the_card_names_who_the_work_waits_on(self):
        spec = self.root / "specs" / "S-1.md"
        note = '\n```aidd-handoff\ndone = "T1"\nnext = "tester"\nneeds = "none"\nstopped_at = "4"\n```\n'
        spec.write_text(spec.read_text(encoding="utf-8") + note, encoding="utf-8")
        self.run_hook("stop", self.stop_event())
        self.assertEqual(self.state(self.comment_set()), "working")  # an uncommitted draft is still the agent's to finish
        # Committed, the draft waits for Spec approval of its hash: the derived status says so, not the note.
        self.commit_all()
        self.log.unlink()
        self.run_hook("stop", self.stop_event())
        self.assertEqual(self.state(self.comment_set()), "waiting on @x")  # owners.approvers
        with_many = SPEC.replace("assisted_by = []", 'assisted_by = []\napprovers = ["@a", "@b", "@c", "@d"]') + note
        spec.write_text(with_many, encoding="utf-8")
        self.assertEqual(self.state(hooks.card_line(self.root)), "waiting on @a, @b +2")

    def test_the_card_says_stuck_when_the_agent_stops_and_nothing_moved(self):
        old = {**os.environ, "GIT_COMMITTER_DATE": "2020-01-01T00:00:00Z", "GIT_AUTHOR_DATE": "2020-01-01T00:00:00Z"}
        git(self.root, "commit", "-q", "--allow-empty", "-m", "long ago", env=old)
        self.run_hook("stop", self.stop_event())
        self.assertTrue(self.state(self.comment_set()).startswith("stuck: no commit or handoff note for "), self.comment_set())
        # A session that starts is working again; the rule is judged only when the agent stops.
        self.assertEqual(self.state(hooks.card_line(self.root)), "working")
        # A fresh handoff note in the Spec counts as movement, and so does a new commit.
        spec = self.root / "specs" / "S-1.md"
        spec.write_text(
            spec.read_text(encoding="utf-8") + '\n```aidd-handoff\ndone = "x"\nnext = "tester"\nneeds = "none"\nstopped_at = "none"\n```\n', encoding="utf-8"
        )
        self.assertEqual(self.state(hooks.card_line(self.root, stopping=True)), "working")
        # The threshold, with a fixed clock.
        head = float(git(self.root, "log", "-1", "--format=%ct"))
        spec.write_text(SPEC, encoding="utf-8")
        just_under = head + (hooks.STUCK_MINUTES - 1) * 60
        self.assertEqual(self.state(hooks.card_line(self.root, stopping=True, now=just_under)), "working")
        self.assertIn("stuck", hooks.card_line(self.root, stopping=True, now=head + hooks.STUCK_MINUTES * 60))

    def test_the_card_turns_red_when_the_latest_evidence_failed(self):
        head = git(self.root, "rev-parse", "HEAD")
        self.write_evidence(head, names=("app", "lint"), status="failed")
        self.run_hook("stop", self.stop_event())
        self.assertEqual(self.state(self.comment_set()), "red: app, lint failed on HEAD")
        self.write_evidence(head, names=("app",), status="passed")
        self.assertEqual(self.state(hooks.card_line(self.root)), "working")
        # Evidence for another commit, or a red run on the base, is not the head's state.
        self.write_evidence("0" * 40, status="failed")
        self.assertEqual(self.state(hooks.card_line(self.root)), "working")

    def test_a_long_step_is_shortened_and_the_state_kept(self):
        long_title = SPEC.replace('id = "S-1"', 'id = "S-1-' + "x" * 200 + '"')
        (self.root / "specs" / "S-1.md").write_text(long_title, encoding="utf-8")
        line = hooks.card_line(self.root)
        self.assertEqual(len(line), hooks.MAX_CARD_LINE)
        self.assertTrue(line.endswith("..." + hooks.CARD_STATE_SEP + "working"), line)

    def test_through_the_real_entry_point(self):
        env = os.environ | ORCA_ENV | {"PATH": self.path, "FAKE_ORCA_LOG": str(self.log)}
        run = aidd_subprocess("hook", "session-start", cwd=self.root, input=json.dumps(self.event("SessionStart", source="startup")), env=env)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stderr, "")
        self.assertEqual(json.loads(run.stdout)["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertTrue(self.comment_set().startswith(hooks.CARD_PREFIX))


@unittest.skipUnless(shutil.which("git"), "git is required")
class PreCompactTests(HookCase):
    def test_is_a_no_op_at_every_level(self):
        # PreCompact output can only block the compaction; Claude Code discards its systemMessage and it takes no
        # additionalContext. The handoff reminder arrives through session-start with source "compact" instead.
        for level in cfgmod.HOOK_LEVELS:
            self.set_hooks(f'level = "{level}"')
            self.assertEqual(call("pre-compact", self.event("PreCompact", trigger="auto", custom_instructions=None)), (0, "", ""), level)
        run = aidd_subprocess("hook", "pre-compact", cwd=self.root, input=json.dumps(self.event("PreCompact", trigger="manual")))
        self.assertEqual((run.returncode, run.stdout), (0, ""))


@unittest.skipUnless(shutil.which("git"), "git is required")
class GuardLogTests(HookCase):
    def pre_tool(self, event: dict) -> dict:
        out = io.StringIO()
        self.assertEqual(guard.pre_tool_hook(io.StringIO(json.dumps(event)), out), 0)
        return json.loads(out.getvalue())["hookSpecificOutput"] if out.getvalue() else {}

    def log(self) -> list[dict]:
        path = self.root / guard.GUARD_LOG
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.is_file() else []

    def test_each_deny_appends_one_line_without_contents(self):
        secret = "TOP-SECRET-CONTENT"
        edit = {"tool_name": "Write", "cwd": str(self.root), "tool_input": {"file_path": str(self.root / "src/other/y.py"), "content": secret}}
        self.assertEqual(self.pre_tool(edit)["permissionDecision"], "deny")
        allowed = {"tool_name": "Write", "cwd": str(self.root), "tool_input": {"file_path": str(self.root / "src/app/x.py"), "content": secret}}
        self.assertEqual(self.pre_tool(allowed), {})
        (entry,) = self.log()
        self.assertEqual(set(entry), {"ts", "decision", "role", "helper", "tool", "path", "reason"})
        self.assertEqual((entry["role"], entry["tool"], entry["path"], entry["reason"]), (None, "Write", "src/other/y.py", "out_of_scope"))
        self.assertNotIn(secret, (self.root / guard.GUARD_LOG).read_text(encoding="utf-8"))
        # The log is local working state: git never sees it.
        self.assertNotIn(".aidd/work", git(self.root, "status", "--porcelain", "--untracked-files=all"))

    def test_a_denied_command_is_logged_truncated_with_the_role(self):
        command = "gh pr merge 3 " + "x" * 500
        event = {"tool_name": "Bash", "cwd": str(self.root), "agent_type": "aidd-team:developer", "tool_input": {"command": command}}
        self.assertEqual(self.pre_tool(event)["permissionDecision"], "deny")
        (entry,) = self.log()
        self.assertEqual((entry["role"], entry["tool"], entry["reason"]), ("developer", "Bash", "approve_or_merge"))
        self.assertEqual(entry["command"], command[:200])
        helper = {"tool_name": "Edit", "cwd": str(self.root), "agent_type": "Explore", "tool_input": {"file_path": "src/app/x.py"}}
        self.pre_tool(helper)
        self.assertEqual((self.log()[-1]["helper"], self.log()[-1]["reason"]), (True, "helper_read_only"))

    def test_a_logged_command_carries_no_secret(self):
        secrets = {
            "gh pr merge 3 -H 'Authorization: Bearer abc.DEF-123'": "abc.DEF-123",
            "gh api -X PUT -H 'Authorization: token s3cr3t-value' repos/o/r/pulls/1/merge": "s3cr3t-value",
            "GITHUB_TOKEN=ghx-live-000 gh pr merge 1": "ghx-live-000",
            "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI gh pr merge 1": "wJalrXUtnFEMI",
            "DEPLOY_KEY='k e y' gh pr merge 1": "k e y",
            "MY_SECRET_THING=hunter2 gh pr merge 1": "hunter2",
            "gh pr merge 1 --password hunter3": "hunter3",
            "gh pr merge 1 --token=tok-999": "tok-999",
            "git push --force https://bot:p4ssw0rd@github.com/o/r.git main": "p4ssw0rd",
            "gh pr merge 1 # ghp_" + "a" * 36: "ghp_" + "a" * 36,
        }
        for command, secret in secrets.items():
            with self.subTest(command=command):
                self.assertNotIn(secret, guard.redact(command))
                event = {"tool_name": "Bash", "cwd": str(self.root), "tool_input": {"command": command}}
                self.assertEqual(self.pre_tool(event)["permissionDecision"], "deny")
                self.assertNotIn(secret, self.log()[-1]["command"])
                self.assertIn("***", self.log()[-1]["command"])
        self.assertNotIn("p4ssw0rd", (self.root / guard.GUARD_LOG).read_text(encoding="utf-8"))
        # What is not a secret stays, so the log still says what was denied.
        self.assertEqual(guard.redact("gh pr merge 3 --squash"), "gh pr merge 3 --squash")
        self.assertIn("https://bot:***@github.com/o/r.git main", guard.redact("git push --force https://bot:p4ssw0rd@github.com/o/r.git main"))

    def test_a_log_that_cannot_be_written_never_turns_a_deny_into_an_allow(self):
        edit = {"tool_name": "Edit", "cwd": str(self.root), "tool_input": {"file_path": str(self.root / "src/other/y.py")}}
        with mock.patch.object(guard, "log_denial", side_effect=RuntimeError("disk full")):
            self.assertEqual(self.pre_tool(edit)["permissionDecision"], "deny")

    def test_every_deny_family_has_a_code(self):
        root = str(self.root)
        reasons = [
            guard.check_edit(root, "src/other/y.py")[1],
            guard.check_edit(root, ".github/workflows/ci.yml")[1],
            guard.check_edit(root, "src/other/y.py", role="nobody")[1],
            guard.check_edit(root, "docs/x.md", role="developer")[1],
            guard.check_edit(root, "tests/test_app.py", role="developer")[1],
            guard.forbidden_action("gh pr review 1 --approve") or "",
            guard.forbidden_action("gh pr merge 1") or "",
            guard.forbidden_action("glab mr merge 1") or "",
            guard.forbidden_action("gh pr comment 1 --body '/aidd approve'") or "",
            guard.forbidden_action("git push origin refs/aidd/approvals") or "",
            guard.forbidden_action("git push --force origin main") or "",
            guard.forbidden_action("git push --mirror") or "",
            guard.forbidden_action("aidd approve S-1") or "",
            guard.HELPER_DENY,
        ]
        spec = self.root / "specs" / "S-1.md"
        spec.write_text(spec.read_text(encoding="utf-8").replace('kind = "spec"', 'kind = "spec"\nstatus = "ready"', 1), encoding="utf-8")
        reasons.append(guard.check_edit(root, "tests/test_app.py")[1])
        for reason in reasons:
            self.assertNotEqual(guard.reason_code(reason), "other", reason)
        self.assertEqual(guard.reason_code("something new"), "other")


class GuardMetricsTests(unittest.TestCase):
    ENTRIES = [
        {"ts": "2026-09-28T10:00:00Z", "decision": "deny", "role": None, "tool": "Edit", "path": "a", "reason": "out_of_scope"},
        {"ts": "2026-09-28T10:01:00Z", "decision": "deny", "role": "developer", "tool": "Bash", "command": "gh pr merge", "reason": "approve_or_merge"},
        {"ts": "2026-09-28T10:02:00Z", "decision": "deny", "role": "developer", "tool": "Edit", "path": "b", "reason": "out_of_scope"},
    ]

    def test_counts_by_reason_and_role(self):
        counts = metrics.guard_denials(self.ENTRIES)
        self.assertEqual(counts["denials"], 3)
        self.assertEqual(counts["by_reason"], {"out_of_scope": 2, "approve_or_merge": 1})
        self.assertEqual(counts["by_role"], {"developer": 2, "session": 1})
        self.assertEqual(counts["by_tool"], {"Edit": 2, "Bash": 1})

    def test_the_command(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "guard.jsonl"
            log.write_text("\n".join(json.dumps(e) for e in self.ENTRIES) + "\nnot json\n", encoding="utf-8")
            code, out = run_cli("metrics", "--guard", str(log), "--json")
            self.assertEqual(code, 0, out)
            self.assertEqual(json.loads(out)["by_reason"]["out_of_scope"], 2)
            code, out = run_cli("metrics", "--guard", str(log))
            self.assertEqual(code, 0, out)
            self.assertIn("| out_of_scope | 2 |", out)
            self.assertIn("| developer | 2 |", out)
            code, out = run_cli("metrics", "--guard", str(Path(d) / "none.jsonl"))
            self.assertEqual(code, 0, out)
            self.assertIn("No guard denials", out)
            code, out = run_cli("metrics", "--guard", str(log), "--since", "2026-09-28T10:01:30Z", "--json")
            self.assertEqual(json.loads(out)["denials"], 1)

    def test_the_default_path_and_a_missing_argument(self):
        from aidd import cli

        self.assertEqual(cli.build_parser().parse_args(["metrics", "--guard"]).guard, guard.GUARD_LOG)
        code, out = run_cli("metrics")
        self.assertEqual(code, 2)
        self.assertIn("--guard", out)

    def test_the_default_path_is_the_repositorys_from_any_subdirectory(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(str(root), "init", "-q")
            log = root / guard.GUARD_LOG
            log.parent.mkdir(parents=True)
            log.write_text("\n".join(json.dumps(e) for e in self.ENTRIES) + "\n", encoding="utf-8")
            sub = root / "src" / "deep"
            sub.mkdir(parents=True)
            before = os.getcwd()
            try:
                os.chdir(sub)
                code, out = run_cli("metrics", "--guard", "--json")
            finally:
                os.chdir(before)
            self.assertEqual(code, 0, out)
            self.assertEqual(json.loads(out)["denials"], 3)


class WiringTests(unittest.TestCase):
    """These extend the wiring the pre-tool tests pin (tests/test_guard_hooks.py, tests/test_agent_tools.py): the same
    files now also carry the session hooks."""

    def test_the_plugin_wires_the_session_hooks_fail_open(self):
        data = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        # PreCompact cannot add context: it saves the state in the git directory, and session-start reads it back.
        self.assertEqual(set(data), {"PreToolUse", "SessionStart", "Stop", "SubagentStop", "UserPromptSubmit", "PreCompact"})
        for event, name in (
            ("SessionStart", "session-start"),
            ("Stop", "stop"),
            ("SubagentStop", "stop"),
            ("UserPromptSubmit", "prompt-submit"),
            ("PreCompact", "pre-compact"),
        ):
            ((entry,),) = [e["hooks"] for e in data[event]]
            self.assertNotIn("matcher", data[event][0])  # every source, every agent type
            self.assertIn(f'"$P3" -I -S -c "$L" "$R" aidd hook {name} && exit 0', entry["command"])  # behaviour: tests/test_launcher.py
            self.assertIn("AIDD_HOOK_OFFLINE=1", entry["command"])
            self.assertNotIn("exit 2", entry["command"])  # advisory: never fails closed
            self.assertLessEqual(entry["timeout"], 10)

    def test_init_wires_the_session_hooks_once_and_uninstall_removes_only_them(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            settings = root / ".claude" / "settings.json"
            settings.parent.mkdir()
            mine = {"hooks": [{"type": "command", "command": "say done"}]}
            settings.write_text(json.dumps({"hooks": {"Stop": [mine]}}), encoding="utf-8")
            actions: list[str] = []
            repo.install_agent_hooks(root, actions)
            repo.install_agent_hooks(root, actions)
            data = json.loads(settings.read_text(encoding="utf-8"))["hooks"]
            for event, sub in repo.SESSION_EVENTS.items():
                self.assertEqual(sum(h["command"] == repo.hook_command(sub) for e in data[event] for h in e["hooks"]), 1, event)
            self.assertIn(mine, data["Stop"])
            self.assertEqual(repo.session_hooks_missing(settings), [])
            repo.uninstall(root, yes=True)
            left = json.loads(settings.read_text(encoding="utf-8"))["hooks"]
            self.assertEqual(left, {"Stop": [mine]})

    def test_doctor_reports_the_session_hooks(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            make_repo(root, "team", branch=None, agent_hooks=True)
            (root / ".claude").mkdir(exist_ok=True)
            with mock.patch.object(repo, "detect_harnesses", return_value=["claude-code"]):
                self.assertIn(
                    ("ok", "Claude Code: the session hooks (SessionStart, Stop, SubagentStop, UserPromptSubmit, PreCompact) are wired"), repo.doctor(root)
                )
                settings = root / ".claude" / "settings.json"
                data = json.loads(settings.read_text(encoding="utf-8"))
                del data["hooks"]["Stop"]
                settings.write_text(json.dumps(data), encoding="utf-8")
                self.assertTrue(any(lvl == "warn" and "session hooks Stop are not wired" in m for lvl, m in repo.doctor(root)))

    def test_with_the_plugin_enabled_the_session_hooks_are_not_wired_twice(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            settings = root / ".claude" / "settings.json"
            settings.parent.mkdir()
            settings.write_text(json.dumps({"enabledPlugins": {f"aidd@{repo.MARKETPLACE}": True}}), encoding="utf-8")
            self.assertTrue(repo.plugin_enabled(root))
            actions: list[str] = []
            repo.install_agent_hooks(root, actions)
            data = json.loads(settings.read_text(encoding="utf-8"))
            self.assertEqual(repo.session_hooks_wired(settings), [])
            self.assertTrue(any(h["command"] == repo.hook_command("pre-tool") for e in data["hooks"]["PreToolUse"] for h in e["hooks"]))
            self.assertTrue(any("the aidd plugin is enabled" in a for a in actions), actions)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".claude").mkdir()
            (root / ".claude" / "settings.json").write_text(json.dumps({"enabledPlugins": {f"aidd@{repo.MARKETPLACE}": False}}), encoding="utf-8")
            self.assertFalse(repo.plugin_enabled(root))
            (root / ".claude" / "settings.local.json").write_text(json.dumps({"enabledPlugins": {f"aidd@{repo.MARKETPLACE}": True}}), encoding="utf-8")
            self.assertTrue(repo.plugin_enabled(root))

    def test_doctor_warns_when_the_plugin_and_the_settings_both_run_the_session_hooks(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            make_repo(root, "team", branch=None, agent_hooks=True)
            settings = root / ".claude" / "settings.json"
            with mock.patch.object(repo, "detect_harnesses", return_value=["claude-code"]):
                self.assertFalse(any("runs twice" in m for _, m in repo.doctor(root)))
                data = json.loads(settings.read_text(encoding="utf-8"))
                data["enabledPlugins"] = {f"aidd@{repo.MARKETPLACE}": True}
                settings.write_text(json.dumps(data), encoding="utf-8")
                warned = [m for lvl, m in repo.doctor(root) if lvl == "warn" and "runs twice" in m]
                self.assertEqual(len(warned), 1, warned)
                self.assertIn("SessionStart, Stop, SubagentStop", warned[0])
                for event in repo.SESSION_HOOKS:
                    del data["hooks"][event]
                settings.write_text(json.dumps(data), encoding="utf-8")
                found = repo.doctor(root)
                self.assertFalse(any("runs twice" in m or "are not wired" in m for _, m in found), found)

    def test_the_managed_template_gets_the_session_hooks_from_the_force_enabled_plugin(self):
        # Under allowManagedHooksOnly, hooks of a plugin force-enabled in managed `enabledPlugins` still run, so the
        # template does not repeat them (each would run twice), the guard included; AIDD_HOOK_FAIL_CLOSED
        # makes the plugin's guard block when it cannot run (tests/test_managed_settings.py).
        data = json.loads((ROOT / "templates" / "claude" / "managed-settings.json").read_text(encoding="utf-8"))
        self.assertNotIn("hooks", data)
        self.assertEqual(data["env"]["AIDD_HOOK_FAIL_CLOSED"], "1")
        self.assertTrue(data["allowManagedHooksOnly"])
        self.assertIn(True, data["enabledPlugins"].values())


@unittest.skipIf(os.name == "nt" or not shutil.which("sh"), "the hook command runs under a POSIX shell")
class FailOpenCommandTests(unittest.TestCase):
    """What `aidd init --agent-hooks` writes: an aidd that is missing or too old never blocks a session or a stop."""

    def run_command(self, command: str, path: str, env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["sh", "-c", command], input="{}", env={"PATH": path, **(env or {})}, capture_output=True, text=True, timeout=20, encoding="utf-8"
        )

    def test_missing_or_failing_aidd_exits_zero_and_output_passes_through(self):
        with tempfile.TemporaryDirectory() as d:
            sh_dir = str(Path(shutil.which("sh") or "/bin/sh").parent)
            path = os.pathsep.join(dict.fromkeys([sh_dir, "/usr/bin", "/bin"]))
            if shutil.which("aidd", path=path):
                self.skipTest("aidd is installed next to sh; cannot build a PATH without it")
            for command in set(repo.SESSION_HOOKS.values()):
                self.assertEqual(self.run_command(command, path).returncode, 0, command)
            # The interpreter form init writes when aidd is not on PATH fails open the same way.
            gone = repo.hook_command("stop", ([str(Path(d) / "no-python"), "-m", "aidd"], {"PYTHONPATH": str(Path(d) / "src")}))
            self.assertEqual(self.run_command(gone, path).returncode, 0, gone)
            fake = Path(d) / "aidd"
            fake.write_text('#!/bin/sh\necho \'{"decision": "block", "reason": "r"}\'\nexit "${AIDD_FAKE_EXIT:-0}"\n', encoding="utf-8")
            fake.chmod(0o755)
            with_fake = os.pathsep.join([d, path])
            for code in ("0", "2"):
                r = self.run_command(repo.SESSION_HOOKS["Stop"], with_fake, {"AIDD_FAKE_EXIT": code})
                self.assertEqual(r.returncode, 0, code)
                self.assertEqual(json.loads(r.stdout)["decision"], "block")


if __name__ == "__main__":
    unittest.main()
