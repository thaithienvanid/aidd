"""Sixteen roles, one writer per file.

The product manager writes the Specs, the tracking plan, the Initiative's and Epic's brief, the feedback log, and a
proposal's goal, needs, and options; the delivery manager the qualification, the RAID log, the milestones, the
questions, the engagement's contract and change orders, and the acceptance record. Where the delivery manager is not
installed, the product manager does its work (`fallback`). The support analyst is folded in: issue triage goes to the
product manager, knowledge-base articles to the tech writer, the feedback log to the product manager, and the support
report to the delivery manager; the support-desk practice skill stays, loaded by both managers. Agents draft feedback
entries with their source; a person confirms each.
"""

import json
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, git

from aidd.guard import edit_check
from aidd.docsgen import counts
from aidd.setup import adoption
from aidd.knowledge import owners, team_registry
from aidd.kernel import json_schema, resources

TEAM = ROOT / "plugins" / "aidd-team"
SPECIALISTS = ["architect", "product-designer", "security-engineer", "compliance-analyst", "sre", "delivery-manager"]


def roles() -> dict:
    return team_registry.roles()


class TheRoster(unittest.TestCase):
    def test_seventeen_roles_and_no_support_analyst(self):
        data = roles()
        self.assertEqual(len(data["order"]), 17)
        self.assertEqual(counts.count("roles"), 17)
        self.assertNotIn("support-analyst", data["roles"])
        self.assertFalse((TEAM / "agents" / "support-analyst.md").exists())
        self.assertNotIn("support-analyst", owners.DEFAULT_PROACTIVE_ROLES)
        self.assertNotIn("support-analyst", json.dumps(data))
        self.assertNotIn("support-report", data["loop"]["artifacts"])
        self.assertIn(f"<!-- aidd:gen count:roles -->{counts.count('roles')}<!-- aidd:end --> roles", (ROOT / "docs" / "TEAM.md").read_text(encoding="utf-8"))

    def test_both_managers_load_the_support_desk(self):
        for key in ("product-manager", "delivery-manager"):
            self.assertIn("support-desk", roles()["roles"][key]["practices"], key)
        self.assertTrue((TEAM / "skills" / "support-desk" / "SKILL.md").is_file())

    def test_retro_starts_with_the_agile_coach(self):
        retro = next(f for f in roles()["loop"]["flows"] if f["command"] == "retro")
        self.assertEqual(retro["runs"], [["agile-coach"]])


class OneWriterPerFile(unittest.TestCase):
    def test_the_product_managers_area(self):
        # The work items, its analytics docs, the decision cards it writes during Plan (`specs/<ID>/explore/`), the
        # feedback log, and the proposals; never another role's documents in a work item's folder.
        writes = ["{specs_dir}", "{docs:analytics}", "{explorations}", "docs/feedback/**", "{proposals_dir}"]
        self.assertEqual(roles()["roles"]["product-manager"]["writes"], writes)

    def test_the_delivery_managers_area(self):
        writes = roles()["roles"]["delivery-manager"]["writes"]
        self.assertIn("{proposals_dir}", writes)
        self.assertIn("{docs:acceptance}", writes)
        self.assertNotIn("docs/specs/client/**", writes)
        self.assertEqual([k for k, r in roles()["roles"].items() if "{docs:acceptance}" in r["writes"]], ["delivery-manager"])

    def test_the_industry_names(self):
        self.assertEqual(
            roles()["roles"]["delivery-manager"]["industry"],
            "delivery manager; engagement manager, project manager, technical program manager, delivery lead",
        )

    def test_propose_runs_the_managers_then_the_specialists(self):
        propose = next(f for f in roles()["loop"]["flows"] if f["command"] == "propose")
        self.assertEqual(propose["runs"], [["delivery-manager"], ["product-manager"], SPECIALISTS, ["tech-writer"]])

    def test_the_feedback_log_is_a_path_the_product_manager_writes(self):
        feedback = roles()["loop"]["artifacts"]["feedback"]
        self.assertEqual(feedback["kind"], "path")
        self.assertIn("a person confirms", feedback["where"])
        writers = [k for k, r in roles()["roles"].items() if "docs/feedback/**" in r["writes"]]
        self.assertEqual(writers, ["product-manager"])
        self.assertIn("a person confirms", (ROOT / ".agents" / "skills" / "aidd" / "assets" / "feedback.md").read_text(encoding="utf-8"))


class Fallback(unittest.TestCase):
    def test_the_field(self):
        self.assertEqual(roles()["roles"]["delivery-manager"]["fallback"], "product-manager")
        props = resources.load_json("roles.schema.json")["properties"]["roles"]["additionalProperties"]["properties"]
        self.assertIn("fallback", props)
        self.assertEqual(json_schema.validate(resources.load_json("roles.json"), "roles.schema.json"), [])

    def test_the_product_managers_agent_file_covers_for_it(self):
        text = (TEAM / "agents" / "product-manager.md").read_text(encoding="utf-8")
        self.assertIn("delivery-manager", text.split("<!-- aidd:end -->", 1)[0])
        self.assertIn("not installed", text)

    def test_aidd_owners_names_who_covers(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            agents = root / ".claude" / "agents"
            agents.mkdir(parents=True)
            for key in roles()["order"]:
                if key != "delivery-manager":
                    (agents / f"aidd-{key}.md").write_text("x", encoding="utf-8")
            r = owners.owners_view(None, root=root)
            dm = next(a for a in r["agents"] if a["role"] == "delivery-manager")
            self.assertEqual((dm["installed"], dm["fallback"]), (False, "product-manager"))
            self.assertIn("`product-manager` does its work", owners.owners_markdown(r))
            self.assertEqual(json_schema.validate({"schema_version": "1"} | r, "owners.schema.json"), [])
        everyone = owners.owners_view(None)
        self.assertTrue(all(a["installed"] for a in everyone["agents"]))


class TheFeedbackGuard(unittest.TestCase):
    """Only the product manager writes the feedback log; the tech writer's docs area stops at it."""

    def test_only_the_product_manager(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q", "-b", "main")
            adoption.init(root, adoption.InitOptions(profile="team", ci="none", links=[], skill=False, approvers=["@x"], harnesses=[]))
            self.assertEqual(edit_check.check_edit(str(root), "docs/feedback/launch.md", "tech-writer")[0], "deny")
            self.assertEqual(edit_check.check_edit(str(root), "docs/feedback/launch.md", "product-manager")[0], "allow")


if __name__ == "__main__":
    unittest.main()
