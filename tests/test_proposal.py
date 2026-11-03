"""Proposals: the case put to a client or to the company's own decision makers, before any code, with the two human
decisions on record, and the bridge to delivery once it is accepted."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import git, RepoTemplateCase, src_pythonpath

from aidd.workitems import validation
from aidd.setup import adoption
from aidd.workitems import spec_file

BASE = """---
aidd_version: "1.0.0"
type: proposal
id: PROP-1
title: Checkout rebuild
audience: client
addressee: Acme Corp
goal: "Checkout succeeds on the first try for 99% of shoppers"
status: {status}
{top}
needs:
  - id: N-1
    need: Pay by card
    source: RFP 3.2
    answer: met
    epic: Payments

  - id: N-2
    need: Pay by invoice
    answer: partly_met
    epic: Payments
    note: Business customers only

  - id: N-3
    need: Same-day delivery
    answer: not_met

  - id: N-4
    need: Order history
    answer: met

estimate:
  unit: person-days
  low: 40
  likely: 55
  high: 90
  basis: three comparable checkouts
---

## Summary
"""
GO = 'go_no_go: {decision: go, by: "@lead", decided_on: "2026-09-01"}\n'
SIGNED = 'sign_off: {by: "@lead", decided_on: "2026-09-20"}\n'
ACCEPTED = 'outcome: {decision: accepted, by: "@lead", decided_on: "2026-09-25"}\n'
SUBMITTED = 'outcome: {decision: submitted, by: "@lead", decided_on: "2026-09-21"}\n'


def load(status="qualifying", top=""):
    return spec_file.load_object(BASE.format(status=status, top=top), "p.md")


class DecisionTests(unittest.TestCase):
    def test_a_fresh_proposal_needs_no_decision_yet(self):
        self.assertEqual(load()[2], [])

    def test_drafting_needs_a_person_to_have_said_go(self):
        errors = load("drafting")[2]
        self.assertTrue(any("go_no_go.decision" in e for e in errors), errors)
        self.assertEqual(load("drafting", GO)[2], [])

    def test_sending_needs_a_sign_off(self):
        self.assertTrue(any("needs sign_off" in e for e in load("submitted", GO)[2]))
        self.assertTrue(any("needs `outcome" in e for e in load("submitted", GO + SIGNED)[2]))
        self.assertEqual(load("submitted", GO + SIGNED + SUBMITTED)[2], [])
        self.assertTrue(any("outcome submitted needs sign_off" in e for e in load("submitted", GO + SUBMITTED)[2]))

    def test_every_decision_records_its_date_as_decided_on(self):
        """go_no_go, sign_off, and the outcome all say `decided_on` (triage: `triaged_on`); `decided_at` is no name of it."""
        self.assertEqual(load("submitted", GO + SIGNED + SUBMITTED)[2], [])
        self.assertTrue(load("submitted", GO + SIGNED + SUBMITTED.replace("decided_on:", "decided_at:"))[2])
        undated = 'outcome: {decision: submitted, by: "@lead"}\n'
        self.assertTrue(load("submitted", GO + SIGNED + undated)[2])
        self.assertIn("decided_on: YYYY-MM-DD", " ".join(load("accepted", GO + SIGNED)[2]))

    def test_the_status_is_derived_from_the_decisions_and_the_outcome(self):
        """Store only the person's decisions: the status follows from go_no_go, sign_off, and outcome."""
        no_go = 'go_no_go: {decision: no_go, by: "@lead", decided_on: "2026-09-01"}\n'
        for top, want in (
            ("", "qualifying"),
            (no_go, "no_go"),
            (GO, "drafting"),
            (GO + SIGNED, "signed_off"),
            (GO + SIGNED + SUBMITTED, "submitted"),
            (GO + SIGNED + ACCEPTED, "accepted"),
        ):
            data = load("qualifying", top)[0]
            self.assertEqual(spec_file.proposal_status(data), want, top)
            no_status = BASE.format(status="x", top=top).replace("status: x\n", "")
            data, _, errors = spec_file.load_object(no_status, "p.md")
            self.assertEqual((spec_file.proposal_status(data), errors), (want, []))  # the status is optional
        # A stale cache warns; a status the schema does not know is an error (1.0.0 is the first release: no old tokens).
        (warn,) = load("qualifying", GO)[2]
        self.assertTrue(warn.startswith("warning: p.md: status qualifying is behind the recorded decisions, which make it drafting"), warn)
        errors = load("ready", GO + SIGNED)[2]
        self.assertTrue(errors and not any(e.startswith("warning:") for e in errors), errors)

    def test_no_go_is_recorded_as_a_decision(self):
        self.assertTrue(load("no_go")[2])
        self.assertEqual(load("no_go", 'go_no_go: {decision: no_go, by: "@lead", decided_on: "2026-09-01", reason: not our market}\n')[2], [])

    def test_the_range_must_be_ordered_and_ids_unique(self):
        bad = BASE.replace("low: 40", "low: 95").replace("id: N-4", "id: N-1")
        errors = spec_file.load_object(bad.format(status="qualifying", top=""), "p.md")[2]
        self.assertTrue(any("low <= likely <= high" in e for e in errors), errors)
        self.assertTrue(any("needs: ids must be unique (N-1)" in e for e in errors), errors)

    def test_an_agent_account_cannot_decide(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".aidd").mkdir()
            (root / ".aidd" / "config.yaml").write_text(
                'aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@lead"]\nidentities:\n  bots: ["claude[bot]"]\n', encoding="utf-8"
            )
            folder = root / "proposals" / "PROP-1"
            folder.mkdir(parents=True)
            (folder / "proposal.md").write_text(BASE.format(status="drafting", top=GO.replace("@lead", "claude[bot]")), encoding="utf-8")
            errors, _ = validation.check_repo(root)
            self.assertTrue(any("go_no_go.by claude[bot] is an agent account" in e for e in errors), errors)


@unittest.skipUnless(shutil.which("git"), "git is required")
class GuardTests(RepoTemplateCase):
    """Proposal work comes before any Spec: the roles that write a proposal may do so with no Spec active, in the
    proposals folder only, and nobody who builds code writes there."""

    @classmethod
    def build_template(cls, root):
        git(root, "init", "-q", "-b", "main")
        adoption.init(root, adoption.InitOptions(profile="team", ci="none", links=[], skill=False, approvers=["@x"], harnesses=[]))


class CliTests(unittest.TestCase):
    def test_new_and_validate_from_the_command_line(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            env = os.environ | {"PYTHONPATH": src_pythonpath()}
            run = lambda *a: subprocess.run([sys.executable, "-m", "aidd", *a], cwd=d, env=env, capture_output=True, text=True, encoding="utf-8")  # noqa: E731
            made = run("new", "proposal", "PROP-9", "--title", "Move billing to the cloud", "--audience", "internal", "--addressee", "the executive committee")
            self.assertEqual(made.returncode, 0, made.stderr)
            path = Path(d) / "proposals" / "PROP-9" / "proposal.md"
            self.assertIn("audience: internal", path.read_text(encoding="utf-8"))
            self.assertEqual(run("validate", str(path)).returncode, 0)


if __name__ == "__main__":
    unittest.main()
