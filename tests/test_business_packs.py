"""Business packs (V10): each domain of the product's users names its words (`## Terms`) and what is always true in it
with the case a plan misses (`## Invariants and missed cases`), which the domain expert's card checks the work against.
Commerce, education, HR, insurance, logistics, and games are packs of their own; payments covers lending and crypto-assets,
health covers life sciences, the public sector covers defense, and devices cover robots."""

import unittest

from helpers import ROOT

from aidd.docsgen import pack_render
from aidd.knowledge import team_registry

BUSINESS = {
    "payments-and-finance",
    "commerce-and-marketplaces",
    "health",
    "embedded-automotive-industrial",
    "public-sector",
    "products-for-children",
    "education",
    "hr-and-workforce",
    "insurance",
    "logistics-and-supply-chain",
    "games-and-interactive-media",
}


def packs() -> dict[str, dict]:
    return {d["slug"]: d for d in team_registry.roles()["domains"]}


class BusinessPackTests(unittest.TestCase):
    def test_the_business_packs_are_the_ones_named(self):
        self.assertEqual({s for s, d in packs().items() if d["kind"] == "business"}, BUSINESS)

    def test_each_business_pack_renders_its_terms_and_invariants(self):
        for slug in BUSINESS:
            with self.subTest(slug=slug):
                d = packs()[slug]
                text = pack_render.render_pack(d)
                self.assertIn("## Terms", text)
                self.assertIn("| Always true | The case a plan misses |", text)
                for t in d["terms"]:
                    self.assertIn(f"- **{t['term']}**: {t['meaning']}", text)
                self.assertIn(
                    text.split("## Terms", 1)[1].split("## Standards", 1)[0],
                    (ROOT / "plugins/aidd-team/skills" / slug / "SKILL.md").read_text(encoding="utf-8"),
                )

    def test_payments_covers_lending_and_crypto_assets(self):
        ids = packs()["payments-and-finance"]["standards"]
        for sid in ("eu-consumer-credit-directive", "us-consumer-credit-regulations", "mica", "eu-digital-operational-resilience-act"):
            self.assertIn(sid, [s if isinstance(s, str) else s["id"] for s in ids])

    def ids(self, slug: str) -> list[str]:
        return [s["id"] for s in packs()[slug]["standards"]]

    def test_health_covers_life_sciences(self):
        # GxP lives in the health pack's life-sciences reference, which the pack names, so the pack has room for EU rules.
        self.assertIn("fda-qmsr-and-computer-software-assurance", self.ids("health"))
        self.assertIn("eu-health-software-mdr-ivdr-ehds", self.ids("health"))
        ref = (ROOT / "plugins" / "aidd-team" / "skills" / "health" / "references" / "life-sciences.md").read_text(encoding="utf-8")
        for must in ("GxP audit trail test", "21 CFR Part 11", "Annex 11"):
            self.assertIn(must, ref, must)
        self.assertIn("references/life-sciences.md", [r["path"] for r in packs()["health"]["references"]])

    def test_public_sector_covers_defense(self):
        for sid in ("cmmc-dfars-7012-nist-sp-800-171", "itar"):
            self.assertIn(sid, self.ids("public-sector"))
        self.assertIn("ITAR residency check", [t["name"] for t in packs()["public-sector"]["tests"]])

    def test_devices_cover_robots(self):
        self.assertIn("eu-machinery-regulation-and-robot-safety", self.ids("embedded-automotive-industrial"))

    def test_insurance_reuses_the_ai_act_and_dora_entries(self):
        for sid in ("eu-ai-act", "eu-digital-operational-resilience-act", "double-entry-and-idempotent-money-movement"):
            self.assertIn(sid, self.ids("insurance"))


if __name__ == "__main__":
    unittest.main()
