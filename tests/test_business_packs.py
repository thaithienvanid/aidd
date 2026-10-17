"""Business packs (V10): each domain of the product's users names its words (`## Terms`) and what is always true in it
with the case a plan misses (`## Invariants and missed cases`), which the domain expert's card checks the work against.
Commerce, education, and HR are packs of their own; payments covers lending and crypto-assets."""

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


if __name__ == "__main__":
    unittest.main()
