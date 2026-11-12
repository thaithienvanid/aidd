"""One home per phase: the proposal holds what was promised, the Intent the delivery record.

A proposal phase has a `due` date and finishes when a person records `finished_on` or when every Spec its trigger names has
landed; a finished phase is never late. Once accepted, each becomes a phase of the Intent, which takes the
whole RAID log too, and the rollup reads an accepted proposal as history, so nothing is counted twice. Every RAID list holds one
item shape, and only an `open` item is open.
"""

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd.workitems import proposal, spec_file
from aidd.kernel import resources

TODAY = dt.date(2026, 9, 30)
ASSETS = ROOT / ".agents" / "skills" / "aidd" / "assets"

ACCEPTED = """---
aidd_version: "1.0.0"
type: proposal
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
    answer: full

phases:
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


def source(phases: list[dict], item_type: str = "intent", **extra) -> tuple[str, dict]:
    return (f"specs/{item_type}.md", {"type": item_type, "id": "INTENT-1", "phases": phases, **extra})


class MilestoneSchema(unittest.TestCase):
    def test_due_and_finished_on(self):
        props = resources.load_json("proposal.schema.json")["$defs"]["phase"]
        self.assertIn("due", props["required"])
        self.assertNotIn("date", props["properties"])
        self.assertIn("finished_on", props["properties"])
        _, _, errors = spec_file.load_object(ACCEPTED.replace('due: "2026-09-15"', 'date: "2026-09-15"'), "p.md")
        self.assertTrue(errors, "a phase's date is `due`")
        _, _, errors = spec_file.load_object(ACCEPTED.replace('due: "2026-09-15"', 'due: "2026-09-15"\n    finished_on: "2026-09-14"'), "p.md")
        self.assertEqual(errors, [])

    def test_the_template_leaves_the_due_date_to_a_person(self):
        text = (ASSETS / "proposal.md").read_text(encoding="utf-8")
        milestone = text.split("\n# phases:", 1)[1].split("\n\n", 1)[0]
        self.assertNotIn('due: "{{today}}"', milestone)
        self.assertNotIn("{{today}}", "\n".join(ln for ln in milestone.splitlines() if not ln.lstrip().startswith("#")))


class OneHomePerPhase(unittest.TestCase):
    """Convert copies the milestones and the RAID log; the accepted proposal is history, so nothing counts twice."""

    def converted(self) -> tuple[dict, dict]:
        data, _, errors = spec_file.load_object(ACCEPTED, "proposals/PROP-9/proposal.md")
        self.assertEqual(errors, [])
        with tempfile.TemporaryDirectory() as d:
            paths = proposal.convert_proposal(data, Path(d))
            init = next(p for p in paths if p.name.startswith("INTENT-"))
            parsed, _, errors = spec_file.load_object(init.read_text(encoding="utf-8"), str(init))
        self.assertEqual(errors, [])
        return data, parsed

    def test_the_intent_reuses_the_proposal_shapes(self):
        props = resources.load_json("intent.schema.json")["properties"]
        for key in ("risks", "assumptions", "issues", "dependencies"):
            items = props[key]["items"]
            self.assertEqual(items.get("$ref") or items["allOf"][0]["$ref"], "urn:aidd:1:proposal#/$defs/raid_item", key)
        self.assertEqual(props["decisions"]["items"]["$ref"], "urn:aidd:1:proposal#/$defs/decision")
        # A milestone becomes a phase: its trigger keeps the milestone's shape, and its invoicing hook its fields.
        self.assertEqual(props["phases"]["items"]["$ref"], "urn:aidd:1:common#/$defs/phase")
        phase = resources.load_json("common.schema.json")["$defs"]["phase"]
        milestone = resources.load_json("proposal.schema.json")["$defs"]["phase"]
        self.assertEqual(phase["properties"]["trigger"]["$ref"], "urn:aidd:1:proposal#/$defs/phase/properties/trigger")
        self.assertLessEqual(set(milestone["properties"]) - {"finished_on"}, set(phase["properties"]))
        self.assertIn("finished_on", phase["properties"])


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


if __name__ == "__main__":
    unittest.main()
