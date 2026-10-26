"""Autopilot for runs nobody watches: the spend the harness measured, not what a step reported; a stall breaker across
the whole run; a crashed session's lease taken over before its timebox ends; and a notice when the run stops for a
person. Free: no model runs."""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers
import test_autopilot as ta

from aidd import autopilot
from aidd.autopilot import journal, session_transcripts
from aidd.autopilot import lease as leasemod


def _scenario(name):
    return ta.AutopilotScenarioTests.__dict__[name]


class _Run(helpers.RepoTemplateCase):
    build_template = _scenario("build_template")
    write, commit, config, building, approve, take, note = (_scenario(n) for n in ("write", "commit", "config", "building", "approve", "take", "note"))

    def next(self, *, session: str | None = "run-1", minutes: int = 5, **kw) -> dict:
        return autopilot.next_action(self.root, session=session, now=ta.T0 + dt.timedelta(minutes=minutes), **kw)

    def setUp(self):
        super().setUp()
        self.claude = Path(self.tmp.name) / "claude"
        patcher = mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.claude)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def transcript(self, session: str, usages: list[dict], *, subagent: bool = False, when: dt.datetime | None = None) -> Path:
        folder = self.claude / "projects" / "-work-shop"
        path = folder / session / "subagents" / "agent-a.jsonl" if subagent else folder / f"{session}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = (when or ta.T0 + dt.timedelta(minutes=2)).isoformat()
        lines = [json.dumps({"timestamp": stamp, "message": {"role": "assistant", "usage": u}}) for u in usages]
        path.write_text("\n".join([json.dumps({"type": "user", "message": {"content": "hi"}}), *lines]) + "\n", encoding="utf-8")
        return path


class MeasuredSpendTests(_Run):
    def test_the_transcripts_count_the_lead_and_every_subagent_and_leave_cache_reads_out(self):
        self.transcript("run-1", [{"input_tokens": 100, "output_tokens": 50, "cache_creation_input_tokens": 30, "cache_read_input_tokens": 10**9}])
        self.transcript("run-1", [{"input_tokens": 20, "output_tokens": 0}], subagent=True)
        self.transcript("run-1-old", [{"input_tokens": 999}])
        self.assertEqual(session_transcripts.measured_tokens("run-1", ta.T0.isoformat()), 200)
        self.assertEqual(session_transcripts.measured_tokens("run-1", (ta.T0 + dt.timedelta(minutes=3)).isoformat()), 0)  # before the run
        self.assertIsNone(session_transcripts.measured_tokens("no-such-session", ta.T0.isoformat()))
        self.assertEqual(session_transcripts.transcripts("../etc"), [])  # never a path

    def test_the_token_cap_stops_on_the_measured_spend_when_steps_under_report(self):
        self.config("autopilot:\n  max_tokens: 1000")
        self.building()
        self.take()
        self.note("spec.in_progress ok", tokens=10)  # what the step reported
        self.assertEqual(self.next()["action"], "run")
        self.transcript("run-1", [{"input_tokens": 900, "output_tokens": 200}])
        stop = self.next()
        self.assertEqual(stop["reason"], "token_cap")
        self.assertIn("as the session's transcripts show", stop["why"])


class StallBreakerTests(unittest.TestCase):
    def notes(self, *rows):
        return [{"code": c, "spec": s, "head": h, "result": r} for c, s, h, r in rows]

    def test_six_steps_that_move_nothing_stop_the_run(self):
        loop = [("spec.in_progress", "SPEC-1", "a", "fail"), ("spec.verify", "SPEC-2", "b", "fail")] * 3
        self.assertTrue(journal.stalled(self.notes(*loop)))
        again = [("spec.verify", "SPEC-1", "a", "ok")] * 7  # the same step on the same head, again and again
        self.assertTrue(journal.stalled(self.notes(*again)))

    def test_any_progress_keeps_it_going(self):
        rows = [("spec.in_progress", "SPEC-1", "a", "fail")] * 5 + [("spec.in_progress", "SPEC-1", "b", "ok")]  # a new head
        self.assertFalse(journal.stalled(self.notes(*rows)))
        rows = [("spec.in_progress", "SPEC-1", "a", "fail")] * 5 + [("spec.verify", "SPEC-1", "a", "ok")]  # the next step
        self.assertFalse(journal.stalled(self.notes(*rows)))
        self.assertFalse(journal.stalled(self.notes(*[("spec.verify", "SPEC-1", "a", "fail")] * 5)))  # too few to tell


class AbandonedLeaseTests(_Run):
    def test_a_session_gone_quiet_loses_its_lease_before_the_timebox(self):
        self.take(session="crashed")
        path = self.transcript("crashed", [{"input_tokens": 1}])
        quiet = (ta.T0 + dt.timedelta(minutes=1)).timestamp()
        os.utime(path, (quiet, quiet))
        with self.assertRaises(leasemod.LeaseError):  # still busy ten minutes in: it holds its work
            leasemod.take_lease(self.root, session_id="next", now=ta.T0 + dt.timedelta(minutes=10))
        lease, said = leasemod.take_lease(self.root, session_id="next", now=ta.T0 + dt.timedelta(minutes=30))
        self.assertEqual(lease["session_id"], "next")
        self.assertIn("no activity since", said)

    def test_a_session_with_no_transcript_keeps_its_lease_to_its_timebox(self):
        self.take(session="elsewhere")  # another harness: nothing to read
        with self.assertRaises(leasemod.LeaseError):
            leasemod.take_lease(self.root, session_id="next", now=ta.T0 + dt.timedelta(hours=2))


class NoticeTests(_Run):
    def test_a_stop_for_a_person_runs_the_base_branchs_notify_command_once(self):
        log = Path(self.tmp.name) / "notices.log"
        script = Path(self.tmp.name) / "notify.py"
        script.write_text(f"import os, sys\nopen({str(log)!r}, 'a').write(sys.argv[-1] + '|' + os.environ['AIDD_NOTICE'] + '\\n')\n", encoding="utf-8")
        self.config("autopilot:\n  notify: " + json.dumps([sys.executable, str(script)]))
        self.take()
        first = self.next()
        self.assertEqual(first["action"], "stop")
        self.next(minutes=6)  # the same stop again: no second notice
        lines = log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1, lines)
        said, env = lines[0].split("|", 1)
        self.assertEqual(said, env)

    def test_the_working_trees_command_is_never_run(self):
        log = Path(tempfile.mkdtemp()) / "planted.log"
        cfg = self.root / ".aidd" / "config.yaml"
        planted = json.dumps([sys.executable, "-c", f"open({str(log)!r}, 'w').write('ran')"])
        cfg.write_text(cfg.read_text(encoding="utf-8") + f"\nautopilot:\n  notify: {planted}\n", encoding="utf-8")
        self.commit("an agent's config on the branch, never on the base")
        self.take()
        self.assertEqual(self.next(minutes=6 * 60 + 5)["reason"], "timebox")  # a stop a person hears of
        self.assertFalse(log.exists())


if __name__ == "__main__":
    unittest.main()
