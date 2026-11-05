"""Cloud and platform knowledge: pinned Well-Architected editions, the cost of a placement, serverless and edge
performance, telemetry cost, multi-tenant quotas and offboarding, and the device regulations (CRA, UN R155 and R156,
SOTIF, radio equipment). Each fact has one owner; the others point to it."""

import re
import unittest

from helpers import ROOT

from aidd.evals import standards_audit
from aidd.docsgen import pack_budget
from aidd.docsgen import pack_render
from aidd.kernel import documents, resources
from aidd.knowledge import team_registry

SKILLS = ROOT / "plugins" / "aidd-team" / "skills"
DAY = "2026-09-30"


def read(path) -> str:
    return path.read_text(encoding="utf-8")


def raw_pack(slug: str) -> dict:
    return next(d for d in resources.load_json("roles.json")["domains"] if d["slug"] == slug)


def rendered(slug: str) -> str:
    return pack_render.render_pack(next(d for d in team_registry.roles()["domains"] if d["slug"] == slug))


def ids(d: dict) -> list[str]:
    return [s if isinstance(s, str) else s["id"] for s in d["standards"]]


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.table = resources.load_json("roles.json")["standards"]

    def test_each_framework_is_pinned_to_its_dated_edition_with_evidence(self):
        want = {
            "cloud-provider-well-architected-frameworks": "2024-11-06",
            "aws-serverless-lens": "2022-07-14",
            "aws-saas-lens-tenant-isolation": "2023-04-04",
        }
        for sid, published in want.items():
            e = self.table[sid]
            self.assertEqual(e["published"], published, sid)
            self.assertIn(published, e["edition"], sid)
            self.assertGreaterEqual(e["checked"], DAY, sid)  # checked when added, or re-checked since
            self.assertEqual(e["evidence"]["retrieved"], e["checked"], sid)
            self.assertTrue(standards_audit.confirms(e), sid)
        # One entry for the host's framework: each provider's edition is in it, and the pack applies the one its host publishes.
        merged = self.table["cloud-provider-well-architected-frameworks"]
        for edition in ("AWS 2024-11-06", "Google Cloud 2026-01-28", "Cloudflare 2026-06-05", "Azure"):
            self.assertIn(edition, merged["edition"])
        self.assertIn("Azure Well-Architected Framework", merged["notes"])
        for old in ("aws-well-architected-framework", "google-cloud-well-architected-framework", "cloudflare-reference-architectures"):
            self.assertNotIn(old, self.table)
        self.assertEqual(self.table["finops-for-cloud-and-ai-cost"]["edition"], "FinOps Framework 2026")
        self.assertNotIn("well-architected", self.table, "the unpinned generic entry is replaced by the dated ones")

    def test_the_device_regulations_carry_their_dates(self):
        cra = self.table["eu-cyber-resilience-act"]
        self.assertIn("11 December 2027", cra["evidence"]["quote"])
        self.assertIn("11 September 2026", cra["evidence"]["quote"])
        red = self.table["radio-equipment-cybersecurity"]
        self.assertIn("2027-12-11", red["notes"])
        self.assertIn("EN 18031", red["edition"])
        self.assertIn("EN 303 645 V3.1.3", red["edition"])
        self.assertIn("ISO 24089", self.table["un-r155-r156"]["edition"])
        self.assertEqual(self.table["iso-21448-sotif"]["edition"], "ISO 21448:2022")
        self.assertIn("third edition", self.table["iso-26262-and-iso-sae-21434"]["notes"])


class CloudPackTests(unittest.TestCase):
    def setUp(self):
        self.d = raw_pack("cloud-and-infrastructure")
        self.text = rendered("cloud-and-infrastructure")

    def test_the_pinned_frameworks_are_the_packs_standards(self):
        for sid in (
            "cloud-provider-well-architected-frameworks",
            "finops-for-cloud-and-ai-cost",
        ):
            self.assertIn(sid, ids(self.d))
        self.assertLessEqual(len(self.d["standards"]), pack_budget.PACK_STANDARDS)

    def test_the_checklist_asks_for_placement_estimate_tags_budgets_caps_and_actuals(self):
        rows = " ".join(c["item"] for c in self.d["checklist"])
        for need in (
            "references/cost-and-performance.md",
            "10x",
            "`project.budget`",
            "max_infra_per_month",
            "tags",
            "budget with an alert",
            "scales to zero",
            "concurrency or instance cap",
            "pooled",
            "actual cost",
        ):
            self.assertIn(need, rows, need)

    def test_the_cost_tests_are_pinned_commands(self):
        tests = {t["name"]: t["how"] for t in self.d["tests"]}
        # The library standard that fills the choice owns the tool's pin, so the row names the choice.
        self.assertIn("`cost-estimate-tool`'s tests entry", tests["Cost diff threshold"])
        # Infracost v2 replaced `breakdown`/`diff` with `scan`; the row is optional, as a third-party service.
        self.assertIn("scan <dir> --json", tests["Cost diff threshold"])
        self.assertIn("total_monthly_cost", tests["Cost diff threshold"])
        self.assertTrue(tests["Cost diff threshold"].startswith("Optional"))
        self.assertIn("`policy-tool`'s tests entry", tests["Tag and budget policy"])
        plan = tests["Plan or dry-run check"]
        for pinned in (r"aws-cdk@\d", r"wrangler@\d", r"Pulumi v\d", r"--dry-run", r"diff --fail"):
            self.assertRegex(plan, pinned)

    def test_the_reference_holds_the_guide_the_map_and_the_worksheet_with_dated_prices(self):
        ref = read(SKILLS / "cloud-and-infrastructure" / "references" / "cost-and-performance.md")
        for heading in ("## Pick the placement", "## Provider map", "## Limits that decide a placement", "## List prices", "## Break-even worksheet"):
            self.assertIn(heading, ref)
        for provider in ("AWS", "Google Cloud", "Cloudflare", "Azure"):
            self.assertIn(provider, documents.raw_section(ref, "Provider map"))
        self.assertIn(DAY, ref)
        self.assertIn("aidd-team:cloud-and-infrastructure", read(SKILLS / "performance" / "references" / "serverless.md"))
        self.assertIn("references/cost-and-performance.md", self.text)


class PracticeTests(unittest.TestCase):
    def test_performance_has_a_serverless_and_edge_section(self):
        text = read(SKILLS / "performance" / "SKILL.md")
        self.assertIn("references/serverless.md", text.split("### Serverless and edge", 1)[1].split("\n## ", 1)[0])
        part = read(SKILLS / "performance" / "references" / "serverless.md")
        for word in ("cold start", "Init Duration", "SnapStart", "timeout", "pool", "eventually consistent"):
            self.assertIn(word, part, word)
        self.assertIn("aws-serverless-lens", resources.load_json("roles.json")["practices"]["performance"]["standards"])

    def test_observability_owns_telemetry_cost(self):
        text = read(SKILLS / "observability" / "SKILL.md")
        self.assertIn("references/telemetry-cost.md", text)
        self.assertIn("Metric cardinality test", pack_budget.practice_tests(text))
        ref = read(SKILLS / "observability" / "references" / "telemetry-cost.md")
        for word in ("parentbased_traceidratio", "tail_sampling", "cardinality", "Retention", "10x", "aidd-team:cloud-and-infrastructure"):
            self.assertIn(word, ref, word)


class MultiTenantTests(unittest.TestCase):
    def test_quotas_offboarding_and_tenant_cost(self):
        d = raw_pack("multi-tenant-saas")
        rows = " ".join(c["item"] for c in d["checklist"])
        for need in ("per-tenant quota", "Offboarding", "exported", "deleted", "Cost per tenant", "unit economics"):
            self.assertIn(need, rows, need)
        names = [t["name"] for t in d["tests"]]
        self.assertIn("Per-tenant quota enforced", names)
        self.assertIn("Tenant offboarding export and delete", names)
        self.assertIn("SaaS Lens", rendered("multi-tenant-saas"))


class EmbeddedTests(unittest.TestCase):
    def setUp(self):
        self.d = raw_pack("embedded-automotive-industrial")
        self.text = rendered("embedded-automotive-industrial")

    def test_the_regulations_and_their_dates(self):
        for sid in ("eu-cyber-resilience-act", "un-r155-r156", "iso-21448-sotif", "radio-equipment-cybersecurity"):
            self.assertIn(sid, ids(self.d))
        dates = {o["date"] for o in self.d["obligations"]}
        self.assertEqual(
            dates, {"2024-04-29", "2024-07-07", "2025-08-01", "2026-09-11", "2026-09-12", "2026-12-09", "2027-01-20", "2027-12-11"}
        )  # 2024-04-29: UK PSTI; 2026-09-12: Data Act Art. 3(1); 2026-12-09: the Product Liability Directive; 2027-01-20: the Machinery Regulation
        self.assertIn("aidd-team:incident-response", documents.raw_section(self.text, "Dated obligations"))
        self.assertNotIn("72 hours", self.text)

    def test_hardware_in_the_loop_is_conditional(self):
        self.assertRegex(self.text, r"where the project has (a rig|one)")
        self.assertIn("Default credential and open port check", [t["name"] for t in self.d["tests"]])

    def test_the_cra_clock_row_lives_in_incident_response(self):
        clocks = read(SKILLS / "incident-response" / "references" / "breach-clocks.md")
        row = next(r for r in clocks.splitlines() if r.startswith("| EU CRA"))
        for part in ("24 h", "72 h", "14 days", "2026-09-11"):
            self.assertIn(part, row)
        self.assertTrue(re.search(r"eu-cyber-resilience-act", str(resources.load_json("roles.json")["practices"]["incident-response"]["standards"])))


if __name__ == "__main__":
    unittest.main()
