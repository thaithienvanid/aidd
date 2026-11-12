"""A change that costs money to run says what: `aidd validate` warns, and never blocks.

A Spec whose Task scopes hit the `infra` area's paths, or whose risk names `cost`, gives a `cost_estimate` (monthly,
at 10x, and its source); `aidd validate` warns when it gives none, and when the monthly estimate is above
`project.budget.max_infra_per_month` in the same currency. It is a hint: no check fails on it.
"""

import unittest

import helpers  # noqa: F401  (puts src on the path)

from aidd import config
from aidd.config import project

HEAD = 'aidd_version: "1.0.0"\nprofile: team\nowners: {approvers: ["@org/leads"]}\n'
BUDGET = "\nproject:\n  budget:\n    max_infra_per_month: 50\n    currency: EUR\n"


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


class HintFunctionTests(unittest.TestCase):
    def test_the_hint_reads_the_budget_from_the_config(self):
        cfg = config.load_text(HEAD + BUDGET)
        infra = {"tasks": [{"id": "T1", "scope": ["main.tf"]}]}
        over = project.cost_hint(infra | {"risk": {"cost_estimate": {"monthly": "70 EUR"}}}, cfg)
        self.assertIsNotNone(over)
        self.assertIn("max_infra_per_month", over or "")
        self.assertIsNone(project.cost_hint(infra | {"risk": {"cost_estimate": {"monthly": "20 EUR"}}}, cfg))
        self.assertIn("give it in EUR too", project.cost_hint(infra | {"risk": {"cost_estimate": {"monthly": "70 USD"}}}, cfg) or "")
        # Any estimate given meets the budget, whatever the change touches; one that reads as no amount says so.
        self.assertIn("above", project.cost_hint({"tasks": [], "risk": {"cost_estimate": {"monthly": "900 EUR"}}}, cfg) or "")
        self.assertIn("give an amount and its currency", project.cost_hint(infra | {"risk": {"cost_estimate": {"monthly": "1.2k"}}}, cfg) or "")
        self.assertIsNone(project.cost_hint({"tasks": [{"id": "T1", "scope": ["src/app.py"]}]}, None))

    def test_a_cost_risk_needs_an_estimate_too(self):
        costly = {"route": "normal", "risk": {"dimensions": ["cost"]}, "tasks": [{"id": "T1", "scope": ["src/app.py"]}]}
        self.assertIn("its risk names cost", project.cost_hint(costly, None) or "")
        self.assertIsNone(project.cost_hint(costly | {"risk": {"dimensions": ["cost"], "cost_estimate": {"monthly": "10 EUR"}}}, None))
        self.assertIsNone(project.cost_hint(costly | {"route": "minor"}, None))


if __name__ == "__main__":
    unittest.main()
