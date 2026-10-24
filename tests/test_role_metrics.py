"""`aidd metrics --roles`: one row per aidd-team role, from the gate events, the Specs, the guard's log, the trunk's
reverts, and a role eval record file, and never from the autopilot journal; display only, so it always exits 0."""

import contextlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, git, run_cli

from aidd import evals
from aidd.kernel import json_schema, resources
from aidd.tracking import role_metrics

SPEC_1 = """---
kind: spec
id: SPEC-1
title: Paging
status: done
tasks:
  - id: SPEC-1-T1
    title: the code
    scope: ["src/"]
    assignee: agent:developer
    retry_count: 3
  - id: SPEC-1-T2
    title: the tests
    scope: ["src/"]
    assignee: agent:verifier
revisions:
  - "on": "2026-09-01"
    why: The Acceptance missed the first page.
    was: "0123456789abcdef0123456789abcdef"
outcome:
  released_on: "2026-09-02"
  rolled_back: true
---

# Paging
"""

SPEC_2 = """---
kind: spec
id: SPEC-2
title: Search
tasks:
  - id: SPEC-2-T1
    title: the code
    scope: ["lib/"]
    assignee: agent:developer
  - id: SPEC-2-T2
    title: a person's slice
    scope: ["lib/"]
    assignee: "@lead"
---

# Search
"""


def ev(change, ts, spec="SPEC-1", decision="pass", head="a" * 40, **kw):
    return {"repo": "o/r", "change": change, "ts": ts, "decision": decision, "spec_id": spec, "head_sha": head, "pending_rules": [], "failed_rules": []} | kw


def write_specs(root: Path) -> Path:
    specs = root / "specs"
    specs.mkdir(parents=True, exist_ok=True)
    (specs / "SPEC-1.md").write_text(SPEC_1, encoding="utf-8")
    (specs / "SPEC-2.md").write_text(SPEC_2, encoding="utf-8")
    (specs / "README.md").write_text("# Specs\n", encoding="utf-8")
    return specs


class RoleMeasuresTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.specs = role_metrics.spec_roles(write_specs(self.root), self.root)

    def rows(self, events, guard=(), reverts=(), evals_=None):
        out = role_metrics.role_measures(events, self.specs, guard=list(guard), reverts=list(reverts), evals=evals_ or {})
        self.assertEqual(json_schema.validate(out, "metrics.schema.json#/$defs/roles"), [], json.dumps(out)[:400])
        return out, {r["role"]: r for r in out["rows"]}

    def test_one_row_per_role_in_the_order_roles_json_gives(self):
        out, _ = self.rows([])
        self.assertEqual([r["role"] for r in out["rows"]], list(resources.load_json("roles.json")["roles"]))
        self.assertTrue(all(r["too_few_to_judge"] and r["eval"] is None for r in out["rows"]))
        self.assertIs(out["display_only"], True)

    def test_a_spec_measure_counts_in_full_for_each_role_with_a_task_in_it(self):
        events = [
            ev("1", "2026-09-01T09:00:00Z", head="b" * 40, decision="fail", failed_rules=["tests"]),
            ev("1", "2026-09-01T10:00:00Z", head="c" * 40),
            ev("2", "2026-09-02T09:00:00Z", spec="SPEC-2"),
        ]
        _, rows = self.rows(events)
        dev, verifier, pm = rows["developer"], rows["verifier"], rows["product-manager"]
        self.assertEqual((dev["changes"], dev["specs"], verifier["changes"], verifier["specs"], pm["changes"]), (2, 2, 1, 1, 0))
        # Change 1 passed on its second head, change 2 on its first: the developer's share is a half, the verifier's none.
        self.assertEqual((dev["first_pass_share"], verifier["first_pass_share"]), (0.5, 0.0))
        self.assertEqual((dev["failing_heads_per_change"], verifier["failing_heads_per_change"]), (0.5, 1.0))
        # SPEC-1's revision and rollback count for both its roles; its Task out of retries for its assignee alone.
        self.assertEqual((dev["revisions"], dev["rolled_back"], verifier["revisions"], verifier["rolled_back"]), (1, 1, 1, 1))
        self.assertEqual((dev["tasks_out_of_retries"], verifier["tasks_out_of_retries"]), (1, 0))

    def test_a_spec_path_names_its_change_when_the_event_has_no_spec_id(self):
        event = ev("1", "2026-09-01T09:00:00Z", spec=None) | {"spec": "specs/SPEC-2.md"}
        _, rows = self.rows([event])
        self.assertEqual((rows["developer"]["changes"], rows["verifier"]["changes"]), (1, 0))

    def test_the_autopilot_journal_never_counts(self):
        journal = {"kind": "autopilot", "ts": "2026-09-01T09:00:00Z", "change": "9", "spec_id": "SPEC-1", "run": {"event": "step_done"}}
        _, rows = self.rows([journal])
        self.assertEqual(rows["developer"]["changes"], 0)

    def test_ten_changes_are_enough_to_judge(self):
        events = [ev(str(n), f"2026-09-{n + 1:02d}T09:00:00Z") for n in range(10)]
        _, rows = self.rows(events)
        self.assertFalse(rows["developer"]["too_few_to_judge"])
        self.assertTrue(role_metrics.role_measures(events[:9], self.specs, guard=[], reverts=[], evals={})["rows"][8]["too_few_to_judge"])

    def test_guard_denials_count_by_role_and_never_for_the_session(self):
        guard = [{"decision": "deny", "role": "developer"}, {"decision": "deny", "role": None}, {"decision": "allow", "role": "developer"}]
        _, rows = self.rows([], guard=guard)
        self.assertEqual(rows["developer"]["guard_denials"], 1)
        self.assertEqual(sum(r["guard_denials"] for r in rows.values()), 1)

    def test_a_revert_joins_the_spec_of_the_head_it_reverts_else_the_spec_file_it_changed(self):
        events = [ev("2", "2026-09-02T09:00:00Z", spec="SPEC-2", head="d" * 40)]
        reverts = [
            {"sha": "1" * 40, "reverts": "e" * 40, "parents": ["f" * 40, "d" * 40], "paths": ["specs/SPEC-1.md"]},
            {"sha": "2" * 40, "reverts": "9" * 40, "parents": ["8" * 40], "paths": ["src/x.py", "specs/SPEC-1.md"]},
            {"sha": "3" * 40, "reverts": "7" * 40, "parents": [], "paths": []},
        ]
        out, rows = self.rows(events, reverts=reverts)
        # The first joins SPEC-2 by its merged head (the path is not read), the second SPEC-1 by its file, the third nothing.
        self.assertEqual((rows["developer"]["reverts"], rows["verifier"]["reverts"]), (2, 1))
        self.assertEqual((out["reverts"], out["unjoined_reverts"]), (3, 1))

    def test_the_markdown_says_too_few_to_judge_and_no_eval_record(self):
        out, _ = self.rows([])
        text = role_metrics.roles_markdown(out)
        self.assertIn("| developer | 0 |", text)
        self.assertIn("no eval record | too few to judge |", text)
        self.assertIn("never put a role's number into its prompt", text)


class RoleEvalTests(unittest.TestCase):
    def run_line(self, date, scenarios, suite="roles", **kw):
        return {"suite": suite, "date": date, "model": "m", "scenarios": scenarios, "mean_pass_at_1": 0.5} | kw

    def test_the_latest_fresh_run_counts_and_a_stale_one_never(self):
        runs = [
            self.run_line("2026-09-01T00:00:00Z", [{"id": "a", "role": "developer", "pass_at_1": 0.2}, {"id": "b", "role": "verifier", "pass_at_1": 1.0}]),
            self.run_line(
                "2026-09-05T00:00:00Z",
                [
                    {"id": "a", "role": "developer", "pass_at_1": 1.0, "control_pass_at_1": 0.5},
                    {"id": "c", "role": "developer", "pass_at_1": 0.5, "control_pass_at_1": 0.5},
                ],
            ),
            self.run_line("2026-09-09T00:00:00Z", [{"id": "a", "role": "developer", "pass_at_1": 0.0}]),
            self.run_line("2026-09-10T00:00:00Z", [{"id": "a", "role": "developer", "pass_at_1": 0.0}], suite="routing"),
        ]
        out = role_metrics.role_evals(runs, [True, True, False, True])
        self.assertEqual(out["developer"], {"pass_at_1": 0.75, "lift": 0.25, "date": "2026-09-05T00:00:00Z", "model": "m", "scenarios": 2})
        self.assertEqual((out["verifier"]["pass_at_1"], out["verifier"]["lift"]), (1.0, None))
        self.assertEqual(role_metrics.role_evals(runs, [False] * 4), {})
        self.assertIn("75%, lift +25.0 pts", role_metrics._eval_cell(out["developer"]))


class TrunkRevertTests(unittest.TestCase):
    def test_reverts_on_the_trunk_name_the_commit_its_parents_and_its_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            git(root, "init", "-q", "-b", "main")
            (root / "README.md").write_text("r\n", encoding="utf-8")
            git(root, "add", "-A")
            git(root, "commit", "-qm", "day 0")
            write_specs(root)
            git(root, "add", "-A")
            git(root, "commit", "-qm", "SPEC-1 lands")
            landed = git(root, "rev-parse", "HEAD")
            git(root, "checkout", "-qb", "feat")
            (root / "lib.py").write_text("x = 1\n", encoding="utf-8")
            git(root, "add", "-A")
            git(root, "commit", "-qm", "lib")
            head = git(root, "rev-parse", "HEAD")
            git(root, "checkout", "-q", "main")
            git(root, "merge", "-q", "--no-ff", "-m", "merge feat", "feat")
            merge = git(root, "rev-parse", "HEAD")
            git(root, "revert", "--no-edit", "-m", "1", merge)
            git(root, "revert", "--no-edit", landed)
            reverts = {r["reverts"]: r for r in role_metrics.trunk_reverts(str(root), "main")}
            self.assertEqual(set(reverts), {merge, landed})
            self.assertEqual(reverts[merge]["parents"][1], head)
            self.assertEqual(reverts[merge]["paths"], ["lib.py"])
            self.assertIn("specs/SPEC-1.md", reverts[landed]["paths"])
            self.assertEqual(role_metrics.trunk_reverts(str(root), "main", "2099-01-01"), [])


class RolesCliTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        git(self.root, "init", "-q", "-b", "main")
        write_specs(self.root)
        cases = self.root / "evals" / "roles"
        cases.mkdir(parents=True)
        shutil.copy(ROOT / "evals" / "roles" / "scenarios.yaml", cases / "scenarios.yaml")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "day 0")
        self.events = self.root / "events.jsonl"
        self.events.write_text(json.dumps(ev("1", "2026-09-01T09:00:00Z")) + "\n", encoding="utf-8")
        self.material = evals.material_sha256("roles", cases)

    def metrics(self, *args):
        with contextlib.chdir(self.root):
            return run_cli("metrics", str(self.events), "--roles", *args)

    def record(self, material):
        line = {"suite": "roles", "date": "2026-09-05T00:00:00Z", "model": None, "cases": "evals/roles", "material_sha256": material, "mean_pass_at_1": 1.0}
        line["scenarios"] = [{"id": "r04", "role": "developer", "trials": 1, "passed": 1, "pass_at_1": 1.0, "pass_all": True}]
        path = self.root / "evals-results.jsonl"
        path.write_text(json.dumps(line) + "\n", encoding="utf-8")
        return str(path)

    def test_the_json_matches_its_schema_and_exits_0(self):
        code, out = self.metrics("--json", "--eval-record", self.record(self.material))
        self.assertEqual(code, 0, out)
        data = json.loads(out)
        for ref in ("metrics.schema.json#/$defs/roles", "metrics.schema.json"):
            self.assertEqual(json_schema.validate(data, ref), [], ref)
        rows = {r["role"]: r for r in data["rows"]}
        self.assertEqual((rows["developer"]["changes"], rows["verifier"]["changes"]), (1, 1))
        self.assertEqual(rows["developer"]["eval"]["pass_at_1"], 1.0)

    def test_a_stale_eval_record_never_counts(self):
        code, out = self.metrics("--eval-record", self.record("0" * 64))
        self.assertEqual(code, 0, out)
        self.assertIn("| developer | 1 |", out)
        self.assertNotIn("100%", out)
        self.assertIn("no eval record | too few to judge |", out)

    def test_roles_goes_alone_and_eval_record_goes_with_roles(self):
        code, out = self.metrics("--dora")
        self.assertEqual(code, 2, out)
        self.assertIn("--roles goes alone, not with --dora", out)
        with contextlib.chdir(self.root):
            code, out = run_cli("metrics", str(self.events), "--eval-record", "evals-results.jsonl")
        self.assertEqual(code, 2, out)
        self.assertIn("--eval-record goes with --roles", out)
        code, out = self.metrics("--eval-record", "missing.jsonl")
        self.assertEqual(code, 2, out)
        self.assertIn("aidd eval roles --record", out)


if __name__ == "__main__":
    unittest.main()
