"""Two session hooks: the prompt hint, the PreCompact snapshot, and their wiring.

- `aidd hook prompt-submit` (UserPromptSubmit) adds one line to the agent's context with this change's first
  step and its command: only under the team and org profiles, at level balanced or strict. A few tokens, no
  secret, and it never blocks a prompt.
- `aidd hook pre-compact` saves the state of the work in the git directory, never in a tracked file; session-start reads
  it back after the compaction or on resume.
"""

import json
import shutil
import unittest
from unittest import mock

from helpers import ROOT, aidd_subprocess, git
from test_session_hooks import HookCase, call

from aidd.guard import session_hooks
from aidd.tracking import route_forecast
from aidd.setup import hook_wiring
from aidd.autopilot import lease, store

STEP = {"code": "spec.draft", "what": "S-1 needs its Spec finished", "who": "agent", "how": "run `/aidd-team:specify S-1`"}


@unittest.skipUnless(shutil.which("git"), "git is required")
class PromptHintTests(HookCase):
    def hint(self, **extra) -> tuple[int, str, str]:
        return call("prompt-submit", self.event("UserPromptSubmit", prompt="go on", **extra))

    def test_one_line_with_the_step_and_its_command(self):
        code, out, err = self.hint()
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        line = payload["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(len(line.splitlines()), 1, line)
        self.assertLessEqual(len(line), session_hooks.MAX_HINT_CHARS)
        self.assertIn("S-1", line)
        self.assertTrue(line.startswith("aidd: next step: "), line)
        self.assertNotIn("decision", payload)  # never blocks the prompt

    def test_the_command_is_in_the_line(self):
        with mock.patch.object(route_forecast, "forecast", return_value={"route": None, "steps": [STEP], "overlaps": []}):
            _, out, _ = self.hint()
        line = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("/aidd-team:specify S-1", line)
        self.assertIn("agent", line)

    def test_only_team_and_org_at_default_or_strict(self):
        for profile, level, said in (("team", "strict", True), ("team", "minimal", False)):
            with self.subTest(profile=profile, level=level):
                self.set_hooks(f"level: {level}")
                self.assertEqual(bool(self.hint()[1]), said)
        config = self.root / ".aidd" / "config.yaml"
        for profile, said in (("org", True), ("solo", False), ("audited", False)):
            text = config.read_text(encoding="utf-8").split("\nhooks:")[0]
            text = "\n".join(f"profile: {profile}" if line.startswith("profile: ") else line for line in text.splitlines()) + "\n"
            config.write_text(text, encoding="utf-8")
            with self.subTest(profile=profile):
                self.assertEqual(bool(self.hint()[1]), said, profile)

    def test_a_long_step_is_cut_and_a_secret_is_masked(self):
        long = dict(STEP, what="S-1 " + "word " * 200, how="run `deploy --token=ghp_" + "a" * 36 + "`")
        with mock.patch.object(route_forecast, "forecast", return_value={"route": None, "steps": [long], "overlaps": []}):
            _, out, _ = self.hint()
        line = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertLessEqual(len(line), session_hooks.MAX_HINT_CHARS)
        self.assertNotIn("ghp_" + "a" * 36, line)
        long = dict(STEP, how="run it with GITHUB_TOKEN=ghp_" + "b" * 36)
        with mock.patch.object(route_forecast, "forecast", return_value={"route": None, "steps": [long], "overlaps": []}):
            _, out, _ = self.hint()
        self.assertNotIn("b" * 36, out)

    def test_nothing_open_is_quiet(self):
        with mock.patch.object(route_forecast, "forecast", return_value={"route": None, "steps": [], "overlaps": []}):
            self.assertEqual(self.hint(), (0, "", ""))

    def test_a_failure_never_blocks_the_prompt(self):
        with mock.patch.object(route_forecast, "forecast", side_effect=RuntimeError("boom")):
            code, out, _ = self.hint()
        self.assertEqual((code, out), (0, ""))

    def test_through_the_real_entry_point(self):
        run = aidd_subprocess("hook", "prompt-submit", cwd=self.root, input=json.dumps(self.event("UserPromptSubmit", prompt="hi")))
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")


@unittest.skipUnless(shutil.which("git"), "git is required")
class PreCompactSnapshotTests(HookCase):
    def compact(self, session: str = "abc123") -> tuple[int, str, str]:
        return call("pre-compact", self.event("PreCompact", session_id=session, trigger="auto", custom_instructions=None))

    def test_it_saves_the_state_in_the_git_directory_and_nothing_tracked(self):
        before = git(self.root, "status", "--porcelain", "--ignored=no")
        lease.take_lease(self.root, work="S-1", session_id="abc123")
        lease.note_step(self.root, "spec.draft ok specified", session_id="abc123", spec="S-1")
        self.assertEqual(self.compact(), (0, "", ""))  # PreCompact output cannot add context, so it prints nothing
        self.assertEqual(git(self.root, "status", "--porcelain", "--ignored=no"), before)
        saved = lease.saved_snapshot(self.root, "abc123")
        self.assertIsNotNone(saved)
        text = saved["text"]
        self.assertIn("S-1", text)
        self.assertIn("autopilot", text)
        self.assertIn("spec.draft ok", text)
        self.assertTrue((store.lease_store(self.root) / lease.SNAPSHOTS_FILE).is_file())

    def test_session_start_reads_it_back_after_a_compaction_or_a_resume(self):
        self.compact()
        for source in ("compact", "resume"):
            _, out, _ = call("session-start", self.event("SessionStart", source=source))
            context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
            self.assertIn("Before the compaction", context, source)
        _, out, _ = call("session-start", self.event("SessionStart", source="startup"))
        self.assertNotIn("Before the compaction", json.loads(out)["hookSpecificOutput"]["additionalContext"])
        _, out, _ = call("session-start", self.event("SessionStart", source="compact", session_id="another"))
        self.assertNotIn("Before the compaction", json.loads(out)["hookSpecificOutput"]["additionalContext"])

    def test_the_handoff_notes_stopped_at_is_saved(self):
        spec = self.root / "specs" / "S-1.md"
        spec.write_text(
            spec.read_text(encoding="utf-8") + '\n```aidd-handoff\ndone: x\nnext: developer\nstopped_at: "Implement, TASK 2"\n```\n', encoding="utf-8"
        )
        self.compact()
        self.assertIn("Implement, TASK 2", lease.saved_snapshot(self.root, "abc123")["text"])

    def test_no_secret_is_saved(self):
        with mock.patch.object(
            route_forecast, "forecast", return_value={"route": None, "steps": [dict(STEP, how="AWS_SECRET_ACCESS_KEY=abcdEFGH1234 deploy")], "overlaps": []}
        ):
            self.compact()
        self.assertNotIn("abcdEFGH1234", lease.saved_snapshot(self.root, "abc123")["text"])

    def test_it_turns_off_at_minimal(self):
        self.set_hooks("level: minimal")
        self.compact()
        self.assertIsNone(lease.saved_snapshot(self.root, "abc123"))

    def test_a_bad_session_id_or_a_failure_is_quiet(self):
        self.assertEqual(self.compact(session="../../etc"), (0, "", ""))
        with mock.patch.object(lease, "save_snapshot", side_effect=OSError("disk")):
            code, out, _ = self.compact()
        self.assertEqual((code, out), (0, ""))


class WiringTests(unittest.TestCase):
    def test_the_plugin_and_init_wire_both_hooks_fail_open(self):
        data = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        for event, name in (("UserPromptSubmit", "prompt-submit"), ("PreCompact", "pre-compact")):
            ((entry,),) = [e["hooks"] for e in data[event]]
            self.assertIn(f'"$P3" -I -S -c "$L" "$R" aidd hook {name} && exit 0', entry["command"])
            self.assertNotIn("exit 2", entry["command"])
            self.assertLessEqual(entry["timeout"], 10)
            self.assertEqual(hook_wiring.SESSION_EVENTS[event], name)
            self.assertEqual(hook_wiring.aidd_hook(hook_wiring.hook_command(name)), name)
        self.assertEqual(set(session_hooks.HANDLERS), {"session-start", "prompt-submit", "stop", "pre-compact"})


if __name__ == "__main__":
    unittest.main()
