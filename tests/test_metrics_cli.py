"""`aidd metrics` and `aidd upgrade` from the command line: exit codes and the shape of what they print."""

import contextlib
import json
import tempfile
import unittest
from pathlib import Path

from helpers import run_cli

from aidd import __version__, repo


def ev(change, ts, decision="pass", **kw):
    return {"repo": "o/r", "change": change, "ts": ts, "decision": decision, "route": "normal", "pending_rules": [], "failed_rules": []} | kw


EVENTS = [
    ev("1", "2026-09-01T09:00:00Z", "pending"),
    ev("1", "2026-09-01T13:00:00Z", assisted_by=["claude-code/claude-opus-5-5"], type="feat"),
    ev("2", "2026-09-15T09:00:00Z", assisted_by=["claude-code/claude-opus-5-5"], type="fix"),
]


class MetricsCliTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.events = self.root / "events.jsonl"
        self.events.write_text("".join(json.dumps(e) + "\n" for e in EVENTS), encoding="utf-8")

    def metrics(self, *args):
        with contextlib.chdir(self.root):
            return run_cli("metrics", str(self.events), *args)

    def set_targets(self, targets):
        cfg = self.root / ".aidd" / "config.toml"
        if not cfg.is_file():
            repo.init(self.root, profile="team", ci="none", links=[], skill=False, approvers=["@lead"], harnesses=[])
            self.base_config = cfg.read_text(encoding="utf-8")
        cfg.write_text(self.base_config + "\n[targets]\n" + "".join(f"{k} = {v}\n" for k, v in targets.items()), encoding="utf-8")

    def test_dora_without_targets_has_no_verdict_and_exits_0(self):
        code, out = self.metrics("--dora", "--json")
        self.assertEqual(code, 0, out)
        rows = {r["metric"]: r for r in json.loads(out)}
        self.assertEqual(set(rows), {"deployments_per_week", "lead_time_hours", "change_fail_rate", "recovery_days", "rework_rate"})
        self.assertTrue(all(r["target"] is None and r["met"] is None for r in rows.values()))

    def test_dora_exits_1_when_a_target_is_missed(self):
        self.set_targets({"lead_time_hours": 1})  # the median of 4 hours (change 1) and 0 (change 2 passed at once)
        code, out = self.metrics("--dora", "--json")
        self.assertEqual(code, 1, out)
        rows = {r["metric"]: r for r in json.loads(out)}
        self.assertEqual((rows["lead_time_hours"]["value"], rows["lead_time_hours"]["met"]), (2.0, False))
        self.set_targets({"lead_time_hours": 8})
        self.assertEqual(self.metrics("--dora")[0], 0)

    def test_autonomy_rows_name_the_stage(self):
        code, out = self.metrics("--autonomy", "--json")
        self.assertEqual(code, 0, out)
        rows = json.loads(out)
        self.assertEqual([(r["agent"], r["type"]) for r in rows], [("claude-code/claude-opus-5-5", "feat"), ("claude-code/claude-opus-5-5", "fix")])
        self.assertTrue(all("stage" in r and r["changes"] == 1 for r in rows), rows)


class UpgradeCliTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        repo.init(self.root, profile="team", ci="gitlab", links=[], skill=False, approvers=["@lead"], harnesses=[], ref="v1.0.0")
        self.gitlab = self.root / ".gitlab" / "aidd.gitlab-ci.yml"
        self.gitlab.write_text(self.gitlab.read_text(encoding="utf-8").replace("aidd@v1.0.0", "aidd@v0.9.0"), encoding="utf-8")

    def test_a_ref_that_is_not_a_sha_or_tag_is_a_usage_error(self):
        code, out = run_cli("upgrade", str(self.root), "--ref", "main; x")
        self.assertEqual(code, 2)
        self.assertIn("must be a 40-character commit SHA or a release tag", out)

    def test_a_dry_run_says_so_and_changes_nothing(self):
        before = self.gitlab.read_text(encoding="utf-8")
        code, out = run_cli("upgrade", str(self.root), "--ref", "v1.0.0")
        self.assertEqual(code, 0, out)
        self.assertIn("dry run", out)
        self.assertIn(f"would update {self.gitlab}", out)
        self.assertEqual(self.gitlab.read_text(encoding="utf-8"), before)

    def test_the_gitlab_include_is_repinned(self):
        sha = "a" * 40
        lines = repo.upgrade(self.root, ref=sha, yes=True)
        self.assertTrue(any(ln.startswith("updated ") and str(self.gitlab) in ln for ln in lines), lines)
        text = self.gitlab.read_text(encoding="utf-8")
        self.assertIn(f'aidd_pin="thaithienvanid/aidd@{sha}"', text)
        self.assertNotIn("aidd@v0.9.0", text)
        self.assertIn(f'aidd_version = "{__version__}"', (self.root / ".aidd" / "config.toml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
