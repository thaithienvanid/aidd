"""One naming convention for the fields a person or an agent writes, and no field kept for its own sake.

`due` is an object's deadline, `<action>_due` a secondary one, `<event>_on` the date an event happened, and a person's
decision is `{decision?, by, on}` with `by` an identity. So a project rule has `review_due`, a flag `cleanup_due`, a
runbook `tested_on`, and a postmortem `incident_on`. An Epic names one `owner_team`; it is multi-team when its Specs
name several. The qualification keeps what decides a go/no-go; the proposal drops `confidential` and the outcome's
`at`; the preview drops `seed`; a runbook's RTO and RPO are a number and a unit.
"""

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd import config, model, project, proposal, repo, resources, schema

TODAY = dt.date(2026, 9, 30)
IDENTITY = "urn:aidd:1:common#/$defs/identity"


def props(name: str, *path: str) -> dict:
    node = resources.load_json(name)
    for key in path:
        node = node[key]
    return node


class Renames(unittest.TestCase):
    def test_a_project_rule_has_review_due(self):
        rule = props("config.schema.json", "$defs", "project_rule", "properties")
        self.assertIn("review_due", rule)
        self.assertNotIn("review_by", rule)
        cfg = config.load_text(
            'aidd_version = "1.0.0"\nprofile = "team"\n[owners]\napprovers = ["@x"]\n[[project.rules]]\nid = "r"\nlevel = "must"\n'
            'statement = "s"\nwhy = "w"\nowner = "@x"\nreview_due = "2026-01-01"\n'
        )
        _, warnings = project.findings(cfg, TODAY)
        self.assertTrue(any("review_due 2026-01-01 has passed" in w for w in warnings), warnings)

    def test_a_flag_has_cleanup_due(self):
        flag = props("spec.schema.json", "$defs", "flag", "properties")
        self.assertIn("cleanup_due", flag)
        self.assertNotIn("cleanup_by", flag)
        objects = [("specs/SPEC-1.md", {"kind": "spec", "id": "SPEC-1", "flags": [{"name": "f", "cleanup_due": "2026-01-01"}]})]
        self.assertEqual([f["name"] for _, _, f in repo.overdue_flags(objects, TODAY)], ["f"])

    def test_a_runbook_has_tested_on(self):
        rb = props("runbook.schema.json", "properties")
        self.assertIn("tested_on", rb)
        self.assertNotIn("last_tested", rb)
        base = {"aidd_version": "1.0.0", "kind": "runbook", "id": "RB-1", "title": "t", "service": "s", "owner_team": "o", "status": "active"}
        for key in ("rto", "rpo"):
            self.assertEqual(rb[key]["pattern"], r"^\d+(m|h|d)$", key)
            self.assertEqual(schema.validate(dict(base, **{key: "4h"}), "runbook.schema.json"), [])
            self.assertTrue(schema.validate(dict(base, **{key: "4 hours"}), "runbook.schema.json"))
        self.assertEqual(schema.validate(dict(base, tested_on="2026-09-01"), "runbook.schema.json"), [])

    def test_a_postmortem_has_incident_on(self):
        pm = props("postmortem.schema.json")
        self.assertIn("incident_on", pm["properties"])
        self.assertIn("incident_on", pm["required"])
        self.assertNotIn("incident_date", pm["properties"])

    def test_a_decision_is_by_an_identity_on_a_date(self):
        p = props("proposal.schema.json", "properties")
        for key in ("go_no_go", "sign_off", "outcome"):
            self.assertEqual(p[key]["properties"]["by"]["$ref"], IDENTITY, key)
            self.assertIn("on", p[key]["required"], key)
        self.assertNotIn("at", p["outcome"]["properties"])


class Cuts(unittest.TestCase):
    def test_the_qualification_keeps_what_decides(self):
        q = props("proposal.schema.json", "properties", "qualification")
        self.assertEqual(set(q["properties"]), {"fit", "budget", "authority", "decision_process", "recommendation"})
        self.assertEqual(set(q["required"]), set(q["properties"]))

    def test_no_confidential_no_seed_no_owner_teams(self):
        self.assertNotIn("confidential", props("proposal.schema.json", "properties"))
        self.assertNotIn("seed", props("config.schema.json", "properties", "preview", "properties"))
        epic = props("epic.schema.json", "properties")
        self.assertNotIn("owner_teams", epic)
        self.assertEqual(epic["owner_team"]["type"], "string")

    def test_convert_names_one_owner_team_per_epic(self):
        text = (ROOT / "tests" / "test_delivery_record.py").read_text(encoding="utf-8").split('ACCEPTED = """', 1)[1].split('"""', 1)[0]
        data, _, errors = model.load_object(text, "p.md")
        self.assertEqual(errors, [])
        with tempfile.TemporaryDirectory() as d:
            paths = proposal.convert(data, Path(d), owner_team="web")
            epic = next(p for p in paths if p.name.startswith("EPIC-"))
            parsed, _, errors = model.load_object(epic.read_text(encoding="utf-8"), str(epic))
        self.assertEqual(errors, [])
        self.assertEqual(parsed["owner_team"], "web")

    def test_the_templates_use_the_new_names(self):
        assets = ROOT / ".agents" / "skills" / "aidd" / "assets"
        text = {n: (assets / n).read_text(encoding="utf-8") for n in ("runbook.md", "postmortem.md", "epic.md", "proposal.md", "spec.md")}
        self.assertIn("tested_on", text["runbook.md"])
        self.assertIn("incident_on", text["postmortem.md"])
        self.assertIn("owner_team =", text["epic.md"])
        for name, body in text.items():
            for old in ("last_tested", "incident_date", "owner_teams", "confidential", "cleanup_by", "\ntimeline =", '\nrisks = "'):
                self.assertNotIn(old, body, (name, old))


if __name__ == "__main__":
    unittest.main()
