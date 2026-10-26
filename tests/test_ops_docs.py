"""Runbooks and postmortems: `aidd new` writes them from the skill's templates into docs/runbooks and
docs/postmortems, `aidd validate` checks them against their schemas like every other object, and `aidd doctor`
warns when a runbook in use has not been run within `docs.max_runbook_age_days`."""

import datetime as dt
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd import config
from aidd.setup import doctor_checks
from aidd.workitems import validation
from aidd.workitems import authoring
from aidd.workitems import spec_file
from aidd.kernel import documents

CFG = 'aidd_version: "1.0.0"\nprofile: team\n{extra}owners:\n  approvers: ["@a"]\n'
TODAY = dt.date(2026, 9, 28)


def repo_with(extra: str = "") -> tempfile.TemporaryDirectory:
    d = tempfile.TemporaryDirectory()
    (Path(d.name) / ".aidd").mkdir()
    (Path(d.name) / ".aidd" / "config.yaml").write_text(CFG.format(extra=extra), encoding="utf-8")
    return d


def runbook(root: Path, rid: str, **fields: str) -> Path:
    p = authoring.new_object(root, authoring.NewObject(kind="runbook", id=rid, title="Fail over the orders database", owner_team="core"))
    text = p.read_text(encoding="utf-8").replace('service: "TODO: the service or system this procedure operates"', "service: orders")
    for key, value in fields.items():
        if key == "status":
            text = text.replace("status: draft", f"status: {value}", 1)
        else:
            text = text.replace("owner_team: core\n", f'owner_team: core\n{key}: "{value}"\n', 1)
    p.write_text(text, encoding="utf-8")
    return p


class TemplateTests(unittest.TestCase):
    def test_new_writes_each_kind_where_it_belongs_and_it_validates(self):
        with repo_with() as d:
            root = Path(d)
            rb = authoring.new_object(root, authoring.NewObject(kind="runbook", id="RB-1", title="Fail over", owner_team="core"))
            pm = authoring.new_object(
                root, authoring.NewObject(kind="postmortem", id="PM-1", title="Checkout 500s", owner_team="core", spec="INC-481", today=dt.date(2026, 9, 1))
            )
            self.assertEqual((rb.relative_to(root).as_posix(), pm.relative_to(root).as_posix()), ("docs/runbooks/RB-1.md", "docs/postmortems/PM-1.md"))
            for p in (rb, pm):
                errs = validation.validate_file(p)
                self.assertEqual([e for e in errs if not e.startswith("warning: ")], [], p.name)
                self.assertTrue(any("TODO placeholders" in e for e in errs), p.name)  # the template's placeholders are reminders
            data, body = documents.split_front_matter(pm.read_text(encoding="utf-8"))
            self.assertEqual((data["kind"], data["incident_on"], data["spec"], data["severity"]), ("postmortem", "2026-09-01", "INC-481", "sev2"))
            for heading in ("Summary", "Impact", "Timeline", "Root cause", "Contributing factors", "What went well", "Action items", "Lessons"):
                self.assertIn(f"## {heading}\n", body)
            _, body = documents.split_front_matter(rb.read_text(encoding="utf-8"))
            for heading in ("Purpose", "When to use", "Prerequisites", "Steps", "Verification", "Rollback", "Escalation"):
                self.assertIn(f"## {heading}\n", body)
            with self.assertRaises(FileExistsError):
                authoring.new_object(root, authoring.NewObject(kind="runbook", id="RB-1", title="again"))
            with self.assertRaises(ValueError):
                authoring.new_object(root, authoring.NewObject(kind="postmortem", id="PM-2", title="x", spec="not an id"))

    def test_the_schemas_hold_the_fields_that_matter(self):
        good = 'aidd_version: "1.0.0"\nkind: runbook\nid: RB-1\ntitle: t\nservice: orders\nowner_team: core\nstatus: active\n'
        self.assertEqual(spec_file.load_object(f"---\n{good}---\n", "rb")[2], [])
        for broken, field in (
            (good.replace("status: active", "status: live"), "status"),
            (good + "tested_on: last week\n", "tested_on"),
            (good.replace("service: orders\n", ""), "service"),
        ):
            self.assertTrue(any(field in e for e in spec_file.load_object(f"---\n{broken}---\n", "rb")[2]), field)
        pm = 'aidd_version: "1.0.0"\nkind: postmortem\nid: PM-1\ntitle: t\nincident_on: "2026-09-01"\nseverity: sev1\nstatus: published\n'
        self.assertEqual(spec_file.load_object(f"---\n{pm}---\n", "pm")[2], [])
        self.assertTrue(any("severity" in e for e in spec_file.load_object(f"---\n{pm.replace('sev1', 'p1')}---\n", "pm")[2]))
        self.assertTrue(any("kind must be" in e and "runbook" in e for e in spec_file.load_object("---\nkind: memo\n---\n", "x")[2]))

    def test_the_command_writes_both(self):
        with repo_with() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            env = os.environ | {"PYTHONPATH": str(ROOT / "src")}
            for args, where in (
                (["runbook", "RB-7", "--title", "Rotate keys"], "docs/runbooks/RB-7.md"),
                (["postmortem", "PM-7", "--title", "Outage", "--spec", "INC-7"], "docs/postmortems/PM-7.md"),
            ):
                run = subprocess.run([sys.executable, "-m", "aidd", "new", *args], cwd=d, env=env, capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertTrue((Path(d) / where).is_file(), where)
            run = subprocess.run([sys.executable, "-m", "aidd", "validate"], cwd=d, env=env, capture_output=True, text=True, encoding="utf-8")
            self.assertIn("docs/runbooks/RB-7.md: still contains TODO placeholders", run.stdout)
            self.assertIn("docs/postmortems/PM-7.md: spec INC-7 is not in specs/", run.stdout)


class ValidateTests(unittest.TestCase):
    def test_the_repository_check_finds_ops_documents_and_their_spec(self):
        with repo_with() as d:
            root = Path(d)
            (root / "docs" / "runbooks").mkdir(parents=True)
            (root / "docs" / "runbooks" / "RB-1.md").write_text("---\nkind: runbook\nid: RB-1\n---\n", encoding="utf-8")
            errors, _ = validation.check_repo(root)
            self.assertTrue(any("RB-1.md" in e and "aidd_version" in e for e in errors), errors)
            authoring.new_object(root, authoring.NewObject(kind="spec", id="INC-9", title="Backfill", route="emergency", owner_team="core", today=TODAY))
            authoring.new_object(root, authoring.NewObject(kind="postmortem", id="PM-9", title="Outage", owner_team="core", spec="INC-9"))
            _, warnings = validation.check_repo(root, today=TODAY)
            self.assertFalse(any("PM-9.md: spec" in w for w in warnings), warnings)


class DoctorTests(unittest.TestCase):
    def stale(self, extra: str = "", **fields: str) -> list[str]:
        with repo_with(extra) as d:
            runbook(Path(d), "RB-1", **fields)
            return [m for level, m in doctor_checks.runbook_checks(Path(d), config.load_file(config.CONFIG_PATH, d), today=TODAY) if level == "warn"]

    def test_a_runbook_older_than_the_limit_is_warned(self):
        self.assertEqual(
            self.stale(status="active", tested_on="2026-01-01"),
            ["docs/runbooks/RB-1.md: runbook RB-1 was last tested 2026-01-01, 270 days ago (limit 180); run it again and update tested_on"],
        )
        self.assertEqual(self.stale(status="active", tested_on="2026-06-01"), [])  # 119 days: fresh
        self.assertEqual(len(self.stale("docs:\n  max_runbook_age_days: 90\n", status="active", tested_on="2026-06-01")), 1)  # the config sets the limit

    def test_an_active_runbook_never_run_is_warned_and_a_retired_one_is_not(self):
        self.assertEqual(
            self.stale(status="active"), ["docs/runbooks/RB-1.md: active runbook RB-1 has never been tested; run it in a drill and record tested_on"]
        )
        self.assertEqual(self.stale(), [])  # a draft is still being written
        self.assertEqual(self.stale(status="retired", tested_on="2020-01-01"), [])

    def test_doctor_reports_it(self):
        with repo_with() as d:
            runbook(Path(d), "RB-1", status="active", tested_on="2025-01-01")
            found = doctor_checks.doctor(Path(d), today=TODAY)
            self.assertTrue(any(level == "warn" and "runbook RB-1 was last tested 2025-01-01" in m for level, m in found), found)

    def test_the_limit_is_a_positive_number_of_days(self):
        with self.assertRaises(config.ConfigError):
            config.load_text(CFG.format(extra="docs:\n  max_runbook_age_days: 0\n"))
        self.assertEqual(config.load_text(CFG.format(extra="")).max_runbook_age_days, 180)


SPEC = """---
aidd_version: "1.0.0"
kind: spec
id: SPEC-1
title: Rate-limit checkout
owner_team: core
type: feat
route: normal
status: {status}
confidence: high
trace_id: spec-1
assisted_by: [claude-code/claude-opus-5-5]
rollback: Revert.
residual_risk: none

risk:
  summary: Small.
  dimensions: []
  reversible: true

tasks:
  - id: T1
    title: Limit
    scope: [src/limit/]
    proof: "{proof}"

tests:
  files: [tests/test_limit.py, tests/limit/]

  commands:
    - name: limit
      command: [pytest, -q, tests/test_limit.py]
      new_behavior: true
---

## Context

x

## Acceptance

y
"""


class ConsistencyTests(unittest.TestCase):
    """Warnings, never errors, where a Spec's plan and its tests disagree."""

    def warnings(self, status="ready", proof="the `limit` test goes red then green", files=(), suite=True) -> list[str]:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".aidd").mkdir()
            extra = "tests:\n  - name: unit\n    command: [make, test]\n" if suite else ""
            (root / ".aidd" / "config.yaml").write_text(CFG.format(extra="") + extra, encoding="utf-8")
            for f in files:
                (root / f).parent.mkdir(parents=True, exist_ok=True)
                (root / f).write_text("", encoding="utf-8")
            (root / "specs").mkdir()
            p = root / "specs" / "SPEC-1.md"
            p.write_text(SPEC.format(status=status, proof=proof), encoding="utf-8")
            found = validation.validate_file(p)
            self.assertEqual([e for e in found if not e.startswith("warning: ")], [])
            return [e.split(": ", 2)[2] for e in found if "tests.files" in e or "proof names" in e]

    def test_a_frozen_test_file_must_exist_once_the_spec_is_approved(self):
        self.assertEqual(
            self.warnings(),
            [
                "tests.files 'tests/test_limit.py' does not exist, but Spec approval holds; Spec approval froze a test nobody wrote",
                "tests.files 'tests/limit/' does not exist, but Spec approval holds; Spec approval froze a test nobody wrote",
            ],
        )
        self.assertEqual(self.warnings(files=("tests/test_limit.py", "tests/limit/test_a.py")), [])
        self.assertEqual(self.warnings(status="draft"), [])  # a draft may name tests it has not written yet

    def test_a_proof_must_name_a_test_command_that_exists(self):
        ok = ("tests/test_limit.py", "tests/limit/a.py")
        self.assertEqual(self.warnings(files=ok, proof="command `unit` stays green"), [])  # the repository suite counts
        self.assertEqual(
            self.warnings(files=ok, proof="the `limits` test goes red then green"),
            ["task T1: proof names test command 'limits', which is neither in tests.commands nor the repository's `tests`"],
        )
        self.assertEqual(
            self.warnings(files=ok, proof="tests `unit` pass", suite=False),
            ["task T1: proof names test command 'unit', which is neither in tests.commands nor the repository's `tests`"],
        )
        self.assertEqual(self.warnings(files=ok, proof="a screenshot of `/checkout` under load"), [])  # prose, not a command

    def test_a_command_running_a_file_outside_tests_files_stays_an_error(self):
        text = SPEC.format(status="draft", proof="x").replace("command: [pytest, -q, tests/test_limit.py]", "command: [pytest, -q, tests/other.py]")
        _, _, errs = spec_file.load_object(text, "spec")
        self.assertTrue(any("tests/other.py" in e and "not covered by tests.files" in e for e in errs), errs)


class OperabilityContentTests(unittest.TestCase):
    """On-call, the environment inventory, and the Twelve-Factor practices, in the runbook, the platforms page, and
    the observability and CI skills that already own them: no new kind, page, or skill."""

    def section(self, text: str, heading: str) -> str:
        return text.split(f"{heading}\n", 1)[1].split("\n## ", 1)[0]

    def test_the_runbook_has_an_on_call_section(self):
        text = (ROOT / ".agents" / "skills" / "aidd" / "assets" / "runbook.md").read_text(encoding="utf-8")
        on_call = self.section(text, "## On-call")
        for word in ("rota", "escalation", "handover", "paging policy"):
            self.assertIn(word, on_call.lower(), word)

    def test_the_environment_ladder_has_an_inventory(self):
        text = (ROOT / "docs" / "PLATFORMS.md").read_text(encoding="utf-8")
        ladder = self.section(text, "## Environments: local preview first")
        self.assertIn("| Environment | Purpose | Data | Who deploys | URL |", ladder)

    def test_twelve_factor_lives_in_observability_and_ci(self):
        team = ROOT / "plugins" / "aidd-team" / "skills"
        obs = self.section((team / "observability" / "SKILL.md").read_text(encoding="utf-8"), "## Twelve-Factor")
        for word in ("stdout", "sigterm", "disposab", "backing service", "environment", "test:"):
            self.assertIn(word, obs.lower(), word)
        ci = self.section((team / "ci-pipeline" / "SKILL.md").read_text(encoding="utf-8"), "## Twelve-Factor")
        for word in ("build, release, run", "parity", "test:"):
            self.assertIn(word, ci.lower(), word)
        index = (team / "product-defaults" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Twelve-Factor", index)


if __name__ == "__main__":
    unittest.main()
