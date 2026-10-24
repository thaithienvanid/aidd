"""A change that costs money to run says what: `aidd validate` warns, and never blocks.

A Spec whose Task scopes hit the `baseline:iac` paths, or whose risk names `cost`, gives a `cost_estimate` (monthly,
at 10x, and its source); `aidd validate` warns when it gives none, and when the monthly estimate is above
`project.budget.max_infra_per_month` in the same currency. It is a hint: the gate never reads it.
"""

import shutil
import unittest

from helpers import RepoTemplateCase, make_repo
from test_linked_docs import spec_text, warnings

from aidd import config
from aidd.workitems import validation
from aidd.gate import rulebook
from aidd.config import project
from aidd.kernel import resources

TECH = "specs/SPEC-9/tech-spec-cart.md"
HEAD = 'aidd_version: "1.0.0"\nprofile: team\nowners: {approvers: ["@org/leads"]}\n'
BUDGET = "\nproject:\n  budget:\n    max_infra_per_month: 50\n    currency: EUR\n"


def tech_spec(cost_row: str) -> str:
    return (
        "# Tech spec\n\nSpec: SPEC-9.\n\n## Non-functional requirements\n\n| Need | Target | Today | How it is checked |\n"
        f"| --- | --- | --- | --- |\n| Availability | 99.9% | 99.9% | the SLO |\n{cost_row}\n"
    )


class EstimateParsingTests(unittest.TestCase):
    def test_a_monthly_amount_is_read_with_its_currency(self):
        cases = {
            "about 40 EUR a month at today's load": [(40.0, "EUR")],
            "$120/month on Fargate": [(120.0, "USD")],
            "estimated 1,250.50 USD per month": [(1250.5, "USD")],
            "£30 each month": [(30.0, "GBP")],
            "monthly cost: 75 EUR": [(75.0, "EUR")],
            "30 EUR a month today, 240 EUR a month at 10x": [(30.0, "EUR"), (240.0, "EUR")],
        }
        for text, want in cases.items():
            self.assertEqual(project.monthly_estimates(text), want, text)

    def test_a_unit_price_or_a_bare_number_is_not_a_monthly_estimate(self):
        for text in (
            "10x users at under 0.002 USD per request",
            "TODO: e.g. 10x users at under 0.002 USD per request",
            "p95 under 300 ms at 200 requests a second",
            "keep 12 months of logs",
            "0.40 USD per million requests",
        ):
            self.assertEqual(project.monthly_estimates(text), [], text)

    def test_only_an_iso_4217_code_or_a_currency_symbol_is_money(self):
        for text in ("an SLA 99.9 monthly", "SLO 99.5 per month", "the API 3 a month", "TLS 1.3 monthly rotation"):
            self.assertEqual(project.monthly_estimates(text), [], text)
        self.assertEqual(project.monthly_estimates("CHF 40 a month, 25 JPY monthly"), [(40.0, "CHF"), (25.0, "JPY")])

    def test_the_iac_paths_are_the_baseline_rule(self):
        rule = next(r for r in resources.load_json("baseline.json")["risk_rules"] if r["name"] == "baseline:iac")
        self.assertEqual(project.IAC_PATHS, rule["paths"])

    def test_it_is_no_gate_rule(self):
        self.assertNotIn("cost estimate", repr(rulebook.RULES).lower())


@unittest.skipUnless(shutil.which("git"), "git is required")
class CostHintTests(RepoTemplateCase):
    """`aidd validate` on a Spec: the warning, and when it stays quiet."""

    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", branch=None)

    def check(self, *, scope='["infra/terraform/main.tf"]', estimate: str = "", tech: str | None = None, cfg_extra: str = "") -> list[str]:
        if cfg_extra:
            cfg = self.root / ".aidd" / "config.yaml"
            cfg.write_text(cfg.read_text(encoding="utf-8") + cfg_extra, encoding="utf-8")
        entries = []
        if tech is not None:
            (self.root / TECH).parent.mkdir(parents=True, exist_ok=True)
            (self.root / TECH).write_text(tech, encoding="utf-8")
            entries.append(("tech-spec", TECH, False))
        text = spec_text(*entries, scope=scope)
        if estimate:
            text = text.replace("\ntasks:", f"\ncost_estimate: {estimate}\ntasks:", 1)
        p = self.root / "specs" / "SPEC-9.md"
        p.parent.mkdir(exist_ok=True)
        p.write_text(text, encoding="utf-8")
        found = validation.validate_file(p, "specs/SPEC-9.md")
        cost = [e for e in found if "cost_estimate" in e or "cost estimate" in e or "max_infra_per_month" in e]
        self.assertEqual(cost, warnings(cost), "a cost finding is only ever a warning")
        return cost

    def test_an_infra_change_without_an_estimate_warns(self):
        found = self.check()
        self.assertEqual(len(found), 1, found)
        self.assertIn("infra/terraform/main.tf", found[0])
        self.assertIn("cost_estimate", found[0])
        self.assertIn("10x", found[0])

    def test_other_iac_shapes_warn_too(self):
        for scope in ('["deploy/k8s/"]', '["wrangler.jsonc"]', '["infra/cdk/**"]', '["serverless.yml"]'):
            self.assertEqual(len(self.check(scope=scope)), 1, scope)

    def test_a_cost_estimate_in_the_spec_is_quiet(self):
        self.assertEqual(self.check(estimate='{monthly: "30 EUR", at_10x: "180 EUR", source: "infracost diff"}'), [])

    def test_prose_is_never_the_estimate(self):
        # One place for the number: a tech spec's Scale and cost row says how it was reached, and the Spec gives it.
        row = "| Scale and cost | 10x users at 0.002 USD per request | 35 USD a month | the cost estimate on the plan |"
        self.assertEqual(len(self.check(tech=tech_spec(row))), 1)

    def test_a_change_off_the_iac_paths_is_quiet(self):
        self.assertEqual(self.check(scope='["src/cart/"]'), [])
        self.assertEqual(self.check(scope='["vendor/terraform/main.tf"]'), [])

    def test_an_estimate_above_the_budget_warns(self):
        found = self.check(estimate='{monthly: "80 EUR"}', cfg_extra=BUDGET)
        self.assertEqual(len(found), 1, found)
        self.assertIn("80 EUR", found[0])
        self.assertIn("max_infra_per_month", found[0])
        self.assertIn("50 EUR", found[0])

    def test_a_folder_scope_holding_iac_files_warns(self):
        (self.root / "infra" / "modules").mkdir(parents=True)
        (self.root / "infra" / "modules" / "main.tf").write_text('resource "x" "y" {}\n', encoding="utf-8")
        for scope in ('["infra/**"]', '["infra/"]'):
            found = self.check(scope=scope)
            self.assertEqual(len(found), 1, scope)
            self.assertIn("infra/modules/main.tf", found[0])
        self.assertEqual(self.check(scope='["docs/**"]'), [])

    def test_an_estimate_within_the_budget_or_in_another_currency_is_quiet(self):
        self.assertEqual(self.check(estimate='{monthly: "40 EUR", at_10x: "300 EUR"}', cfg_extra=BUDGET), [])
        self.assertEqual(self.check(estimate='{monthly: "90 USD"}', cfg_extra=BUDGET), [])


class HintFunctionTests(unittest.TestCase):
    def test_the_hint_reads_the_budget_from_the_config(self):
        cfg = config.load_text(HEAD + BUDGET)
        infra = {"tasks": [{"id": "T1", "scope": ["main.tf"]}]}
        over = project.cost_hint(infra | {"cost_estimate": {"monthly": "70 EUR"}}, cfg)
        self.assertIsNotNone(over)
        self.assertIn("max_infra_per_month", over or "")
        self.assertIsNone(project.cost_hint(infra | {"cost_estimate": {"monthly": "20 EUR"}}, cfg))
        self.assertIn("give it in EUR too", project.cost_hint(infra | {"cost_estimate": {"monthly": "70 USD"}}, cfg) or "")
        # Any estimate given meets the budget, whatever the change touches; one that reads as no amount says so.
        self.assertIn("above", project.cost_hint({"tasks": [], "cost_estimate": {"monthly": "900 EUR"}}, cfg) or "")
        self.assertIn("give an amount and its currency", project.cost_hint(infra | {"cost_estimate": {"monthly": "1.2k"}}, cfg) or "")
        self.assertIsNone(project.cost_hint({"tasks": [{"id": "T1", "scope": ["src/app.py"]}]}, None))

    def test_a_cost_risk_needs_an_estimate_too(self):
        costly = {"route": "normal", "risk": {"dimensions": ["cost"]}, "tasks": [{"id": "T1", "scope": ["src/app.py"]}]}
        self.assertIn("its risk names cost", project.cost_hint(costly, None) or "")
        self.assertIsNone(project.cost_hint(costly | {"cost_estimate": {"monthly": "10 EUR"}}, None))
        self.assertIsNone(project.cost_hint(costly | {"route": "minor"}, None))


if __name__ == "__main__":
    unittest.main()
