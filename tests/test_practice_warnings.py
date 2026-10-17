"""Practices that enforce themselves: the authorization matrix (a linked doc the security engineer writes and the tester
turns into one test per cell), an unrecorded hypothesis outcome, a client's acceptance before ship, and the restore
drill of a stateful service. Each is a warning from `aidd validate` or `aidd doctor`, never a gate rule, and each
reuses a mechanism that already exists: the required-docs matrix, and the runbook staleness check."""

import datetime as dt
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, RepoTemplateCase, aidd_subprocess, git, make_repo, open_work
from test_linked_docs import errors, spec_text, warnings

from aidd.setup import doctor_checks
from aidd.workitems import validation
from aidd.workitems import spec_warnings
from aidd.workitems import authoring
from aidd.config import loading
from aidd.config import model
from aidd.workitems import spec_file
from aidd.kernel import documents, resources
from aidd.knowledge import team_registry

SKILL = ROOT / ".agents" / "skills" / "aidd"
ASSETS = SKILL / "assets"
TEAM = ROOT / "plugins" / "aidd-team"
TODAY = dt.date(2026, 9, 28)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def asks(text: str) -> dict[str, str]:
    data, _ = documents.split_front_matter(text)
    cfg = loading.load_text('aidd_version: "1.0.0"\nprofile: team\n\nowners:\n  approvers: ["@x"]\n')
    return {k: level for k, level, _ in authoring.required_docs(data, len(spec_warnings.acceptance_ids(text)), cfg)}


class AuthzMatrixTemplateTests(unittest.TestCase):
    """One template, one doc kind, and the roles that write and test it."""

    def test_the_template_is_a_matrix_with_a_test_per_cell(self):
        text = read(ASSETS / "authz-matrix.md")
        self.assertIn("{{spec}}", text)
        self.assertIn("{{spec_link}}", text)
        head = "| Subject (role or principal) | Action | Resource or endpoint | Condition (row-level policy) | Expected | Test id |"
        self.assertIn(head, text)
        for heading in ("## Subjects", "## Matrix", "## Row-level policies", "## Tenant isolation", "## Public endpoints"):
            self.assertIn(heading, text)
        self.assertRegex(text, r"(?i)every endpoint requires authentication unless it is listed")
        self.assertIn("| allow |", text)
        self.assertIn("| deny |", text)
        self.assertRegex(text, r"(?i)another tenant")
        self.assertNotRegex(text, r"(?im)^#+ .*sign-off")  # frozen at Spec approval: nothing filled in after it

    def test_the_kind_is_known_everywhere_a_doc_kind_is(self):
        self.assertIn("authz", model.DOC_KINDS)
        self.assertEqual(authoring.DOC_TEMPLATES["authz"], "authz-matrix.md")
        self.assertNotIn("authz", authoring.LIVING_DOCS)
        enum = resources.load_json("spec.schema.json")["$defs"]["doc"]["properties"]["kind"]["enum"]
        self.assertIn("authz", enum)
        self.assertIn("authz", resources.load_json("config.schema.json")["properties"]["docs"]["properties"]["required"]["properties"])

    def test_the_threat_model_links_it_and_the_team_owns_it(self):
        self.assertIn("aidd new authz", read(ASSETS / "threat-model.md"))
        roles = team_registry.roles()["roles"]
        self.assertIn("{docs:authz}", roles["security-engineer"]["writes"])
        self.assertIn("authorization matrix", roles["security-engineer"]["done_when"])
        self.assertIn("authorization matrix", roles["tester"]["done_when"])
        self.assertIn("authorization matrix", read(TEAM / "agents" / "tester.md").split("## Playbook", 1)[1])


class AuthzRequiredDocTests(unittest.TestCase):
    """The required-docs matrix asks for it when the risk names security and a Task touches an auth path."""

    def test_security_on_an_auth_path_warns(self):
        self.assertEqual(asks(spec_text(dims='["security"]', scope='["src/auth/session.py"]')).get("authz"), "warn")
        self.assertEqual(asks(spec_text(route="major", dims='["security"]', scope='["services/rbac/"]')).get("authz"), "warn")

    def test_without_both_conditions_it_stays_quiet(self):
        self.assertNotIn("authz", asks(spec_text(dims='["security"]', scope='["src/cart/"]')))
        self.assertNotIn("authz", asks(spec_text(dims="[]", scope='["src/auth/session.py"]')))
        self.assertNotIn("authz", asks(spec_text(route="minor", dims='["security"]', scope='["src/auth/session.py"]')))

    def test_the_paths_are_the_baseline_auth_rule(self):
        base = next(r for r in resources.load_json("baseline.json")["risk_rules"] if r["name"] == "baseline:auth")
        self.assertEqual(model.default_docs_required()["authz"]["paths"], base["paths"])


class NewAuthzMatrixTests(RepoTemplateCase):
    """`aidd new authz <topic> --spec ID` writes the doc and links it as frozen kind `authz`."""

    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", spec="02-normal-feature:specs/SPEC-220.md")

    def test_new_writes_and_links_it(self):
        run = aidd_subprocess("new", "authz", "Admin API", "--spec", "SPEC-220", cwd=self.root)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        rel = "specs/SPEC-220/authz-admin-api.md"
        self.assertIn("SPEC-220", read(self.root / rel))
        spec = read(self.root / "specs" / "SPEC-220.md")
        self.assertIn(f"docs:\n  - kind: authz\n    path: {rel}\n", spec)
        data, _ = documents.split_front_matter(spec)
        self.assertIn(rel, spec_file.frozen_docs(data))
        self.assertEqual(errors(spec_file.load_object(spec, "specs/SPEC-220.md")[2]), [])

    def test_the_security_engineer_writes_it_unlinked(self):
        run = aidd_subprocess("new", "authz", "Admin API", "--spec", "SPEC-220", "--no-link", cwd=self.root)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("kind: authz", run.stdout)
        self.assertNotIn("frozen: false", run.stdout)


@unittest.skipUnless(shutil.which("git"), "git is required")
class AfterShipTests(RepoTemplateCase):
    """What a shipped Spec still owes, from its own fields, as `aidd validate` warnings."""

    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", branch=None)

    def check(self, text, files=None):
        for rel, body in (files or {}).items():
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text(body, encoding="utf-8")
        p = self.root / "specs" / "SPEC-9.md"
        p.parent.mkdir(exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return warnings(validation.validate_file(p, "specs/SPEC-9.md"))

    def outcome(self, found):
        return [w for w in found if "record the outcome" in w]

    def test_a_past_due_hypothesis_with_no_result_is_warned(self):
        extra = 'status: done\nhypothesis: "Checkout conversion rises from 3.1% to 3.4% by 2026-03-31"\n'
        found = self.outcome(self.check(spec_text(extra=extra)))
        self.assertEqual(len(found), 1, found)
        self.assertIn("2026-03-31", found[0])
        self.assertIn("outcome.result", found[0])

    def test_the_due_date_falls_back_to_the_release_and_the_observe_window(self):
        extra = 'hypothesis: "Checkout conversion rises by 10%"\noutcome: {released_on: "2026-01-10"}\n'
        found = self.outcome(self.check(spec_text(extra=extra)))
        self.assertEqual(len(found), 1, found)
        self.assertIn("2026-01-10", found[0])

    def test_quiet_when_recorded_not_due_or_not_shipped(self):
        due = 'hypothesis: "Conversion rises to 3.4% by 2026-03-31"\n'
        self.assertEqual(self.outcome(self.check(spec_text(extra="status: done\n" + due + 'outcome: {result: "met: 3.5%"}\n'))), [])
        self.assertEqual(self.outcome(self.check(spec_text(extra="status: done\nhypothesis: Conversion rises by 2999-01-01\n"))), [])
        self.assertEqual(self.outcome(self.check(spec_text(extra=due))), [])  # never shipped: nothing to record yet
        self.assertEqual(self.outcome(self.check(spec_text(extra="status: done\nhypothesis: Conversion rises\n"))), [])  # no date to be late by

    def acceptance(self, found):
        return [w for w in found if "acceptance record" in w and "uat" in w]

    def test_uat_in_review_without_an_acceptance_record_is_warned(self):
        found = self.acceptance(self.check(spec_text(extra="status: in_review\nuat: true\n")))
        self.assertEqual(len(found), 1, found)
        self.assertIn("aidd new acceptance", found[0])

    def test_the_record_must_list_every_acceptance_id(self):
        rec = "specs/SPEC-9/acceptance-cart.md"
        body = "# Acceptance record\n\nSpec: SPEC-9.\n\n| Acceptance id | Accepted |\n| --- | --- |\n| A1 | yes |\n"
        found = self.acceptance(self.check(spec_text(("acceptance", rec, False), extra="status: shipped\nuat: true\n"), {rec: body}))
        self.assertEqual(len(found), 1, found)
        self.assertIn("A2", found[0])
        full = body + "| A2 | yes |\n"
        self.assertEqual(self.acceptance(self.check(spec_text(("acceptance", rec, False), extra="status: shipped\nuat: true\n"), {rec: full})), [])

    def test_quiet_before_review_or_without_uat(self):
        self.assertEqual(self.acceptance(self.check(spec_text(extra="status: ready\nuat: true\n"))), [])
        self.assertEqual(self.acceptance(self.check(spec_text(extra="status: in_review\n"))), [])


@unittest.skipUnless(shutil.which("git"), "git is required")
class OutcomeInTheListTests(unittest.TestCase):
    """`aidd list` shows the unrecorded outcome as work, after the Spec itself has left the list."""

    def test_the_list_names_the_outcome_to_record(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d).resolve() / "repo", "team", branch=None)
            (root / "specs").mkdir(exist_ok=True)
            extra = 'status: done\nhypothesis: "Conversion rises to 3.4% by 2026-03-31"\n'
            (root / "specs" / "SPEC-9.md").write_text(spec_text(extra=extra), encoding="utf-8")
            git(root, "add", "-A")
            git(root, "commit", "-qm", "ship SPEC-9")
            steps = [s for s in open_work(root, today=TODAY) if s["where"] == "specs/SPEC-9.md"]
            self.assertEqual([s["code"] for s in steps], ["spec.outcome_due"], steps)
            self.assertIn("outcome.result", steps[0]["how"])


RUNBOOK = """---
aidd_version: "1.0.0"
kind: runbook
id: RB-DB
title: Restore the orders database
service: orders
owner_team: core
status: active
{extra}---

## Steps

1. Restore.
"""


class RestoreDrillTests(unittest.TestCase):
    """A restore runbook states its RTO and RPO, and `aidd doctor` asks for a drill within runbook_max_age_days."""

    def checks(self, extra: str, cfg_extra: str = "") -> list[str]:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".aidd").mkdir()
            (root / ".aidd" / "config.yaml").write_text(f'aidd_version: "1.0.0"\nprofile: team\n{cfg_extra}owners:\n  approvers: ["@a"]\n', encoding="utf-8")
            (root / "docs" / "runbooks").mkdir(parents=True)
            (root / "docs" / "runbooks" / "RB-DB.md").write_text(RUNBOOK.format(extra=extra), encoding="utf-8")
            return [m for level, m in doctor_checks.runbook_checks(root, loading.load_file(model.CONFIG_PATH, d), today=TODAY) if level == "warn"]

    def test_the_schema_holds_rto_rpo_and_restore(self):
        good = RUNBOOK.format(extra='restore: true\nrto: "4h"\nrpo: "15m"\ntested_on: "2026-09-01"\n')
        self.assertEqual(spec_file.load_object(good, "rb")[2], [])
        for broken, field in (("rto: four hours\n", "rto"), ('rpo: "15"\n', "rpo"), ('restore: "yes"\n', "restore")):
            self.assertTrue(any(field in e for e in spec_file.load_object(RUNBOOK.format(extra=broken), "rb")[2]), field)
        props = resources.load_json("runbook.schema.json")["properties"]
        self.assertLessEqual({"restore", "rto", "rpo"}, set(props))

    def test_a_stale_restore_drill_is_warned_as_a_drill(self):
        found = self.checks('restore: true\nrto: "4h"\nrpo: "15m"\ntested_on: "2026-01-01"\n')
        self.assertEqual(len(found), 1, found)
        self.assertIn("restore drill", found[0])
        self.assertIn("2026-01-01", found[0])
        self.assertIn("limit 180", found[0])
        self.assertEqual(self.checks('restore: true\nrto: "4h"\nrpo: "15m"\ntested_on: "2026-09-01"\n'), [])
        self.assertEqual(len(self.checks('restore: true\nrto: "4h"\nrpo: "15m"\ntested_on: "2026-09-01"\n', "runbook_max_age_days: 7\n")), 1)

    def test_a_restore_runbook_never_drilled_or_without_targets_is_warned(self):
        never = self.checks('restore: true\nrto: "4h"\nrpo: "15m"\n')
        self.assertTrue(any("restore drill" in m and "never" in m for m in never), never)
        missing = self.checks('restore: true\ntested_on: "2026-09-01"\n')
        self.assertTrue(any("rto" in m and "rpo" in m for m in missing), missing)

    def test_doctor_reports_it(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".aidd").mkdir()
            (root / ".aidd" / "config.yaml").write_text('aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@a"]\n', encoding="utf-8")
            (root / "docs" / "runbooks").mkdir(parents=True)
            extra = 'restore: true\nrto: "4h"\nrpo: "15m"\ntested_on: "2025-01-01"\n'
            (root / "docs" / "runbooks" / "RB-DB.md").write_text(RUNBOOK.format(extra=extra), encoding="utf-8")
            found = doctor_checks.doctor(root, today=TODAY)
            self.assertTrue(any(level == "warn" and "restore drill" in m for level, m in found), found)

    def test_the_template_and_the_infrastructure_pack_carry_it(self):
        tpl = read(ASSETS / "runbook.md")
        for word in ("rto", "rpo", "restore", "## Restore"):
            self.assertIn(word, tpl)
        pack = next(p for p in team_registry.roles()["domains"] if p["slug"] == "cloud-and-infrastructure")
        items = " ".join(c["item"] for c in pack["checklist"])
        for word in ("RTO", "RPO", "restore drill"):
            self.assertIn(word, items)


class RealDependencyTests(unittest.TestCase):
    """The tester prefers a real throwaway dependency to a mock at the integration level."""

    def test_the_test_design_skill_links_its_testcontainers_reference(self):
        skill = TEAM / "skills" / "test-design"
        text = read(skill / "SKILL.md")
        links = re.findall(r"\]\((references/[^)]+)\)", text)
        self.assertIn("references/real-dependencies.md", links)
        ref = read(skill / "references" / "real-dependencies.md")
        for word in ("Testcontainers", "Python", "Java", ".NET", "Node.js", "Go", "one container per test run", "seed", "mock"):
            self.assertIn(word, ref)
        self.assertRegex(read(TEAM / "agents" / "tester.md").split("## Playbook", 1)[1], r"(?i)real .*mock")
        self.assertRegex(read(ASSETS / "tech-spec.md"), r"(?i)what is real and what is mocked")


class PeopleDocsTests(unittest.TestCase):
    """People management stays human; a new teammate has a checklist."""

    def test_people_management_is_named_human_only(self):
        self.assertRegex(read(ROOT / "docs" / "RATIONALE.md"), r"(?i)engineering management, hiring, and people management")

    def test_a_new_teammate_has_a_checklist(self):
        adoption = read(ROOT / "docs" / "ADOPTION.md")
        self.assertIn("## New teammate", adoption)
        section = adoption.split("## New teammate", 1)[1].split("\n## ", 1)[0]
        for word in ("TEAM.md", "GLOSSARY.md", "Quickstart", "shadow", "Spec approval", "Merge approval", "runbooks"):
            self.assertIn(word, section)

    def test_the_how_to_troubleshooting_and_glossary_cover_the_new_pieces(self):
        self.assertIn("Test access control with a matrix", read(ROOT / "docs" / "HOW-TO.md"))
        trouble = read(ROOT / "docs" / "TROUBLESHOOTING.md")
        for word in ("record the outcome", "acceptance record", "restore drill", "authz"):
            self.assertIn(word, trouble)
        self.assertIn("Authorization matrix", read(ROOT / "docs" / "GLOSSARY.md"))


EXPERIMENT = """
experiment:
  variants: [control, one-page]
  metric: checkout conversion
  guardrails: [payment error rate, p95 checkout latency]
  min_sample: 12000
  decision: ship one-page when conversion rises with p < 0.05 and no guardrail worsens; stop on a guardrail breach or a sample ratio mismatch
"""
HYPOTHESIS = 'hypothesis: "Checkout conversion rises from 3.1% to 3.4% by 2026-12-31"\n'


@unittest.skipUnless(shutil.which("git"), "git is required")
class ExperimentTests(RepoTemplateCase):
    """An A/B test is an optional `experiment` mapping on the Spec that decides its `hypothesis`; `aidd validate` warns,
    never fails, when it names no guardrail metric or the Spec has no hypothesis."""

    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", branch=None)

    def check(self, extra):
        p = self.root / "specs" / "SPEC-9.md"
        p.parent.mkdir(exist_ok=True)
        p.write_text(spec_text(extra=extra), encoding="utf-8")
        return validation.validate_file(p, "specs/SPEC-9.md")

    def about(self, found, word):
        return [w for w in found if "experiment" in w and word in w]

    def test_the_schema_takes_one_primary_metric_and_a_sample_or_a_duration(self):
        found = self.check(HYPOTHESIS + EXPERIMENT)
        self.assertEqual(errors(found), [])
        self.assertEqual(self.about(found, "guardrail") + self.about(found, "hypothesis"), [])
        self.assertEqual(errors(self.check(HYPOTHESIS + EXPERIMENT.replace("min_sample: 12000", 'duration: "14d"'))), [])
        for bad in (
            EXPERIMENT.replace("  min_sample: 12000\n", ""),  # neither a sample nor a duration
            EXPERIMENT.replace("  metric: checkout conversion\n", ""),
            EXPERIMENT.replace("  decision: ", "  rule: "),
            EXPERIMENT.replace("[control, one-page]", "[control]"),  # one arm is not an experiment
            EXPERIMENT.replace("min_sample: 12000", "duration: two weeks"),
        ):
            self.assertNotEqual(bad, EXPERIMENT)
            self.assertTrue(errors(self.check(HYPOTHESIS + bad)), bad)

    def test_no_guardrail_or_no_hypothesis_is_a_warning(self):
        found = self.check(HYPOTHESIS + EXPERIMENT.replace("  guardrails: [payment error rate, p95 checkout latency]\n", ""))
        self.assertEqual(errors(found), [])
        self.assertEqual(len(self.about(found, "guardrail")), 1, found)
        found = self.check(EXPERIMENT)
        self.assertEqual(errors(found), [])
        self.assertEqual(len(self.about(found, "hypothesis")), 1, found)

    def test_the_experiment_is_approved_content(self):
        self.assertNotIn("experiment", spec_file.VOLATILE_SPEC_KEYS)
        self.assertIn("experiment", resources.load_json("spec.schema.json")["properties"])

    def test_the_practice_and_the_tracking_plan_carry_it(self):
        rollout = read(TEAM / "skills" / "release-rollout" / "SKILL.md")
        section = rollout.split("## Experiments", 1)[1].split("\n## ", 1)[0]
        for word in ("sample ratio mismatch", "one primary metric", "guardrail", "stop", "`experiment` block"):
            self.assertIn(word, section, word)
        plan = read(ASSETS / "tracking-plan.md")
        self.assertIn("## Experiment", plan)
        self.assertIn("Experiment Viewed", plan)


if __name__ == "__main__":
    unittest.main()
