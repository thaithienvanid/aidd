"""One home per phase: the proposal holds what was promised, the Initiative the delivery record.

A milestone has a `due` date and is reached when a person records `reached_on` or when every Spec its trigger names has
shipped; a reached milestone is never late. `aidd proposal convert` copies the milestones and the whole RAID log into the
Initiative, and the rollup reads an accepted proposal as history, so nothing is counted twice. Every RAID list holds one
item shape, and only an `open` item is open.
"""

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd.tracking import status_rollup
from aidd.workitems import proposal, spec_file
from aidd.kernel import resources

TODAY = dt.date(2026, 9, 30)
ASSETS = ROOT / ".agents" / "skills" / "aidd" / "assets"

ACCEPTED = """---
aidd_version: "1.0.0"
kind: proposal
id: PROP-9
title: Dealer portal
audience: client
addressee: Acme Corp
goal: Dealers track their orders
go_no_go: {decision: go, by: "@lead", decided_on: "2026-08-01"}
sign_off: {by: "@lead", decided_on: "2026-08-02"}
outcome: {decision: accepted, by: "@lead", decided_on: "2026-08-03"}

needs:
  - id: N-1
    need: Track orders
    answer: met

milestones:
  - id: M-1
    name: Beta
    due: "2026-09-15"
    trigger: {specs: [SPEC-12]}

risks:
  - id: R-1
    text: The ERP export is late
    owner: "@pm"
    status: open
    likelihood: medium
    impact: high

assumptions:
  - id: A-1
    text: Acme provides a read-only ERP export
    owner: Acme IT
    status: open

issues:
  - id: I-1
    text: The staging tenant is not provisioned
    owner: "@ops"
    status: open

dependencies:
  - id: D-1
    text: The payment provider's sandbox account
    owner: Acme finance
    status: resolved
---
"""


def objects(*items: tuple[str, dict]) -> list[tuple[str, dict, str, str]]:
    return [(rel, data, "", "") for rel, data in items]


def source(milestones: list[dict], kind: str = "initiative", **extra) -> tuple[str, dict]:
    return (f"specs/{kind}.md", {"kind": kind, "id": "INIT-1", "milestones": milestones, **extra})


class MilestoneDone(unittest.TestCase):
    """A milestone is reached by a person's `reached_on` or by its trigger Specs shipping; a reached one is never late."""

    def one(self, m: dict, shipped: frozenset[str] = frozenset()) -> dict:
        (got,) = status_rollup.milestones(objects(source([m])), TODAY, shipped)
        return got

    def test_reached_on_makes_it_done_and_never_late(self):
        got = self.one({"id": "M-1", "name": "Beta", "due": "2026-09-01", "reached_on": "2026-09-03", "trigger": {"event": "demo"}})
        self.assertEqual((got["status"], got["late"]), ("done", False))

    def test_every_trigger_spec_shipped_makes_it_done(self):
        m = {"id": "M-1", "name": "Beta", "due": "2026-09-01", "trigger": {"specs": ["SPEC-1", "SPEC-2"]}}
        got = self.one(m, frozenset({"SPEC-1", "SPEC-2"}))
        self.assertEqual((got["status"], got["late"]), ("done", False))
        got = self.one(m, frozenset({"SPEC-1"}))
        self.assertEqual((got["status"], got["late"]), ("open", True))

    def test_an_event_trigger_waits_for_a_person(self):
        got = self.one({"id": "M-1", "name": "Deposit", "due": "2026-09-01", "trigger": {"event": "contract signed"}})
        self.assertEqual((got["status"], got["late"]), ("open", True))

    def test_a_free_form_status_does_not_count(self):
        got = self.one({"id": "M-1", "name": "Beta", "due": "2026-09-01", "status": "done", "trigger": {"event": "x"}})
        self.assertEqual((got["status"], got["late"]), ("open", True))
        self.assertFalse(hasattr(status_rollup, "DONE_MILESTONE"))


class MilestoneSchema(unittest.TestCase):
    def test_due_and_reached_on(self):
        props = resources.load_json("proposal.schema.json")["$defs"]["milestone"]
        self.assertIn("due", props["required"])
        self.assertNotIn("date", props["properties"])
        self.assertIn("reached_on", props["properties"])
        _, _, errors = spec_file.load_object(ACCEPTED.replace('due: "2026-09-15"', 'date: "2026-09-15"'), "p.md")
        self.assertTrue(errors, "a milestone's date is `due`")
        _, _, errors = spec_file.load_object(ACCEPTED.replace('due: "2026-09-15"', 'due: "2026-09-15"\n    reached_on: "2026-09-14"'), "p.md")
        self.assertEqual(errors, [])

    def test_the_template_leaves_the_due_date_to_a_person(self):
        text = (ASSETS / "proposal.md").read_text(encoding="utf-8")
        milestone = text.split("\n# milestones:", 1)[1].split("\n\n", 1)[0]
        self.assertNotIn('due: "{{today}}"', milestone)
        self.assertNotIn("{{today}}", "\n".join(ln for ln in milestone.splitlines() if not ln.lstrip().startswith("#")))


class OneHomePerPhase(unittest.TestCase):
    """Convert copies the milestones and the RAID log; the accepted proposal is history, so nothing counts twice."""

    def converted(self) -> tuple[dict, dict]:
        data, _, errors = spec_file.load_object(ACCEPTED, "proposals/PROP-9/proposal.md")
        self.assertEqual(errors, [])
        with tempfile.TemporaryDirectory() as d:
            paths = proposal.convert_proposal(data, Path(d))
            init = next(p for p in paths if p.name.startswith("INIT-"))
            parsed, _, errors = spec_file.load_object(init.read_text(encoding="utf-8"), str(init))
        self.assertEqual(errors, [])
        return data, parsed

    def test_convert_copies_the_whole_raid_log(self):
        data, init = self.converted()
        for key in ("milestones", "risks", "assumptions", "issues", "dependencies"):
            self.assertEqual(init[key], data[key], key)

    def test_the_initiative_reuses_the_proposal_shapes(self):
        props = resources.load_json("initiative.schema.json")["properties"]
        for key in ("risks", "assumptions", "issues", "dependencies"):
            items = props[key]["items"]
            self.assertEqual(items.get("$ref") or items["allOf"][0]["$ref"], "urn:aidd:1:proposal#/$defs/raid_item", key)
        self.assertEqual(props["milestones"]["items"]["$ref"], "urn:aidd:1:proposal#/$defs/milestone")

    def test_no_double_counting_after_convert(self):
        data, init = self.converted()
        objs = objects(("proposals/PROP-9/proposal.md", data), ("specs/INIT-PROP-9.md", init))
        self.assertEqual([(m["name"], m["source"]) for m in status_rollup.milestones(objs, TODAY, frozenset())], [("Beta", "INIT-PROP-9")])
        self.assertEqual([(r["id"], r["source"]) for r in status_rollup.risks(objs)], [("I-1", "INIT-PROP-9"), ("R-1", "INIT-PROP-9")])


class RaidStatus(unittest.TestCase):
    """One item shape for the four lists, and only `open` is open."""

    def test_one_item_shape(self):
        sch = resources.load_json("proposal.schema.json")
        for key in ("risks", "assumptions", "issues", "dependencies"):
            items = sch["properties"][key]["items"]
            ref = items.get("$ref") or items["allOf"][0]["$ref"]
            self.assertEqual(ref, "#/$defs/raid_item", key)
        item = sch["$defs"]["raid_item"]
        self.assertEqual(item["properties"]["status"]["enum"], ["open", "resolved", "accepted", "invalid"])
        for key in ("likelihood", "impact"):
            self.assertIn(key, item["properties"])

    def test_a_plain_sentence_assumption_is_refused(self):
        block = "assumptions:\n  - id: A-1\n    text: Acme provides a read-only ERP export\n    owner: Acme IT\n    status: open\n\n"
        self.assertIn(block, ACCEPTED)
        text = ACCEPTED.replace(block, "").replace("\nneeds:", "\nassumptions: [The ERP export exists]\n\nneeds:", 1)
        _, _, errors = spec_file.load_object(text, "p.md")
        self.assertTrue(errors, "an assumption is a RAID item with an owner and a status")

    def test_accepted_invalid_and_resolved_are_closed(self):
        items = [
            {"id": f"R-{i}", "text": f"risk {s}", "owner": "@pm", "status": s, "likelihood": "low", "impact": "low"}
            for i, s in enumerate(("open", "resolved", "accepted", "invalid"), 1)
        ]
        issues = [{"id": "I-1", "text": "an issue that was not one", "owner": "@pm", "status": "invalid"}]
        got = status_rollup.risks(objects(source([], risks=items, issues=issues)))
        self.assertEqual([r["id"] for r in got], ["R-1"])
        self.assertFalse(hasattr(status_rollup, "CLOSED"))


if __name__ == "__main__":
    unittest.main()
