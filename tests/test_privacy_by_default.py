"""Privacy by default: personal data routes on the privacy dimension, the data map records it, and a pack says what to do.

A change that touches a user, customer, account, member, patient, or contact model or folder, a file named for personal
data, or adds an authentication library routes on `baseline:personal-data` with the privacy dimension, which forces major
and names the privacy pool. The required-docs matrix then warns for the compliance doc (its DPIA) and suggests the data
map, the one living file that is both the inventory and the records of processing (GDPR Art. 30). The
`privacy-by-default` domain pack applies on the privacy dimension or a `gdpr` compliance target.
"""

import contextlib
import json
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, git, run_cli

from aidd import config
from aidd.evals import suites
from aidd.workitems import authoring
from aidd.kernel import documents, resources
from aidd.knowledge import team_registry

BARE_TEAM = 'aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@a", "@b"]\n'
ASSETS = ROOT / ".agents" / "skills" / "aidd" / "assets"
PACK = ROOT / "plugins" / "aidd-team" / "skills" / "privacy-by-default"


def cfg(text: str = BARE_TEAM) -> config.Config:
    return config.load_text(text)


class PersonalDataRuleTests(unittest.TestCase):
    """`baseline:personal-data`: the privacy dimension, so major and the privacy pool, on personal-data paths only."""

    HITS = [
        "src/users/service.py",
        "app/models/user.rb",
        "src/models/User.ts",
        "api/customers/handlers.go",
        "src/profile/settings.tsx",
        "web/app/accounts/page.tsx",
        "services/members/repo.py",
        "clinic/patients/intake.py",
        "crm/contacts/sync.ts",
        "db/schema/customers.sql",
        "prisma/models/customer.prisma",
        "src/privacy/export.py",
        "lib/pii_redactor.py",
        "src/consent/banner.tsx",
        "jobs/gdpr_erasure.py",
    ]
    MISSES = [
        "docs/users/guide.md",
        "src/users/README.md",
        "tests/users/test_signup.py",
        "tests/fixtures/customers.json",
        "src/profiler/flame.py",
        "src/checkout/cart.py",
        "node_modules/users/index.js",
        "src/users/signup.test.ts",
    ]

    def test_routing_scenarios_hold_the_rule(self):
        scenarios = {
            s["id"]: s for s in documents.parse_yaml((ROOT / "evals" / "routing" / "scenarios.yaml").read_text(encoding="utf-8"), "scenarios.yaml")["scenario"]
        }
        for sid, route in (("c57-customer-profile", "major"), ("c58-auth-library-privacy", "major"), ("c59-profiler-not-personal", "minor")):
            self.assertIn(sid, scenarios)
            self.assertEqual(scenarios[sid]["expected"]["route"], route, sid)
            if not scenarios[sid].get("judgment"):  # a judgment scenario's route is the agent's call, not the paths'
                self.assertEqual(suites.risk_route(scenarios[sid]), route, sid)


class DataMapKindTests(unittest.TestCase):
    """The data map is a living linked doc: the inventory and the records of processing in one file."""

    COLUMNS = (
        "Data item",
        "Category",
        "Purpose",
        "Lawful basis",
        "Source",
        "Systems and stores",
        "Processors",
        "Retention",
        "Deletion method",
        "Transfers",
        "Owner",
    )

    def test_the_kind_is_wired_everywhere(self):

        self.assertIn("data-map", config.DOC_KINDS)
        self.assertEqual(authoring.REPO_DOCS["data-map"], (("{docs}/data-map.md", "data-map.md"),))
        self.assertIn("data-map", authoring.LIVING_DOCS)
        spec_kinds = resources.load_json("spec.schema.json")["$defs"]["doc"]["properties"]["kind"]["enum"]
        self.assertIn("data-map", spec_kinds)
        required = resources.load_json("config.schema.json")["properties"]["docs"]["properties"]["required"]["properties"]
        self.assertIn("data-map", required)
        roles = team_registry.roles()["roles"]
        self.assertIn("docs/data-map.md", roles["compliance-analyst"]["writes"])

    def test_the_template_is_the_records_of_processing(self):
        text = (ASSETS / "data-map.md").read_text(encoding="utf-8")
        self.assertNotIn("{{spec}}", text, "the repository's own, not a Spec's")
        self.assertIn("living", text.split("\n\n", 2)[1].lower())
        self.assertIn("Art. 30", text)
        header = next(line for line in text.splitlines() if line.startswith("| Data item"))
        for column in self.COLUMNS:
            self.assertIn(column, header, column)

    def test_aidd_new_writes_the_one_data_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (path,) = authoring.new_repo_doc(root, kind="data-map")
            self.assertEqual(path.relative_to(root).as_posix(), "docs/data-map.md")
            self.assertNotIn("{{", path.read_text(encoding="utf-8"))
            with self.assertRaises(FileExistsError):
                authoring.new_repo_doc(root, kind="data-map")

    def test_the_cli_offers_it(self):
        with self.assertRaises(SystemExit) as done:
            run_cli("new", "--help")
        self.assertEqual(done.exception.code, 0)
        with tempfile.TemporaryDirectory() as tmp, contextlib.chdir(tmp):  # a repository of its own, wherever the tests run
            git(Path(tmp), "init", "-q")
            code, out = run_cli("new", "data-map", "customers")
        self.assertNotEqual(code, 0)
        self.assertIn("belongs to the repository", out)


class RequiredDocsTests(unittest.TestCase):
    """On the privacy dimension the compliance doc (its DPIA) is warned for, and the data map suggested."""

    def found(self, route: str, dims: list[str]) -> dict[str, str]:
        data = {"route": route, "change_type": "feat", "risk": {"dimensions": dims, "reversible": True}, "tasks": []}
        return {kind: level for kind, level, _ in authoring.required_docs(data, 2, cfg())}

    def test_privacy_warns_for_the_dpia_and_suggests_the_data_map(self):
        for route in ("normal", "major"):
            got = self.found(route, ["privacy"])
            self.assertEqual(got.get("compliance"), "warn", route)
            self.assertEqual(got.get("data-map"), "suggest", route)

    def test_no_privacy_no_ask(self):
        got = self.found("major", ["security"])
        self.assertNotIn("compliance", got)
        self.assertNotIn("data-map", got)

    def test_compliance_analyst_starts_on_privacy(self):
        starts = team_registry.roles()["roles"]["compliance-analyst"]["starts_when"]
        self.assertIn("`personal_data` area", starts)


class PackTests(unittest.TestCase):
    """The privacy-by-default pack: registered, generated, and named by `aidd risk --paths` when it applies."""

    def entry(self) -> dict:
        return next(d for d in team_registry.roles()["domains"] if d["slug"] == "privacy-by-default")

    def test_registered_with_every_step_and_the_rights_tests(self):
        d = self.entry()
        steps = {c["step"] for c in d["checklist"]}
        self.assertLessEqual({"Entry", "Specify", "Implement", "Review", "Roll out"}, steps)
        text = json.dumps(d)
        for art in ("Art. 5", "Art. 6", "Art. 7", "Art. 13", "Art. 15", "Art. 16", "Art. 17", "Art. 18", "Art. 20", "Art. 21"):
            self.assertIn(art, text, art)
        for art in ("Art. 28", "Art. 30", "Art. 32", "Art. 33", "Art. 35", "Art. 44"):
            self.assertIn(art, text, art)
        self.assertIn("CCPA", text)
        names = " ".join(t["name"].lower() for t in d["tests"])
        for word in ("erase", "export"):
            self.assertIn(word, names)

    def test_generated_skill_and_reference(self):
        skill = (PACK / "SKILL.md").read_text(encoding="utf-8")
        description = skill.split('description: "', 1)[1].split('"\n', 1)[0]
        self.assertTrue(description.startswith("In an aidd repository, "), description)
        self.assertLessEqual(len(description), 200)
        self.assertIn("data-map", skill)
        ref = PACK / "references" / "rights-and-records.md"
        self.assertTrue(ref.is_file())
        self.assertIn("references/rights-and-records.md", skill)


if __name__ == "__main__":
    unittest.main()
