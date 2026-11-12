"""The claim registry (evals/claims.json) is closed: a case claims only what an owner lists, and every listed claim has a case or a reason."""

import unittest

from helpers import ROOT

from aidd import evals
from aidd.evals import claim_registry, claims
from aidd.kernel import json_schema

FILE = evals.claims_file(ROOT)


def row(*claim: str, suite: str = "team") -> dict:
    return {"suite": suite, "id": "a", "claims": list(claim), "tier": "full", "proves": "p", "tags": []}


class RegistryTests(unittest.TestCase):
    def test_the_file_follows_its_schema_and_agrees_with_the_files_that_own_its_facts(self):
        self.assertEqual(json_schema.validate(FILE, "eval-claims.schema.json"), [])
        self.assertEqual(claim_registry.registry_problems(FILE, ROOT), [])

    def test_each_claim_of_each_kind_is_checked_against_its_owner(self):
        cases = {
            "an action in risks.json": ("action:pr.merge", True),
            "an action risks.json lacks": ("action:pr.mrege", False),
            "an area": ("route:payments", True),
            "a route outcome the registry lists": ("route:minor-docs", True),
            "a route outcome nobody lists": ("route:minor-nothing", False),
            "a gate": ("gate:merge-approval", True),
            "a gate nobody lists": ("gate:lunch", False),
            "a stop": ("stop:scope-must-widen", True),
            "a stop nobody lists": ("stop:scope-must-narrow", False),
            "a duty of a role": ("duty:reviewer.finds-the-defect", True),
            "a duty of the lead": ("duty:lead.picks-the-mvp-path", True),
            "a duty under the wrong role": ("duty:sre.finds-the-defect", False),
            "a duty with no role": ("duty:finds-the-defect", False),
            "a control": ("control:frozen-tests", True),
            "a principle": ("principle:text-is-data", True),
            "a principle nobody lists": ("principle:be-nice", False),
            "a trigger": ("trigger:debugging", True),
            "a kind nobody owns": ("thing:x", False),
            "no name": ("control:", False),
        }
        for name, (claim, ok) in cases.items():
            with self.subTest(name):
                self.assertEqual(claim_registry.is_registered(claim, FILE), ok)

    def test_a_case_that_names_a_claim_nobody_lists_fails(self):
        self.assertEqual(claims.case_problems([row("control:frozen-tests", "duty:lead.picks-the-mvp-path")], FILE), [])
        (problem,) = claims.case_problems([row("duty:lead.invents-a-duty")], FILE)
        self.assertIn("not in the registry", problem)
        self.assertEqual(claims.case_problems([row("duty:lead.invents-a-duty")]), [], "without the registry the shape is all that is checked")

    def test_every_case_of_the_suites_names_only_registered_claims(self):
        self.assertEqual(evals.case_problems(evals.suite_cases(ROOT), FILE), [])

    def test_the_checker_names_each_way_the_registry_disagrees_with_its_owners(self):
        broken = {
            "a gate on no action": {"gates": {"merge-approval": "pr.mrege"}},
            "a stop on no stop code": {"stops": {"go-no-go": "pause"}},
            "a stop on the code that says done": {"stops": {"go-no-go": "none"}},
            "a route that is not one": {"routes": {"minor-docs": "tiny"}},
            "a duty of no role": {"duties": {"intern": ["makes-coffee"]}},
            "duties out of order": {"duties": {"lead": ["b-duty", "a-duty"]}},
            "a name that is not words": {"duties": {"lead": ["Picks The Path"]}},
            "a control with no source file": {"controls": {"x": {"source": "no/such/file.md", "statement": "s"}}},
            "a principle on a stop code that is none": {"principles": {"x": {"source": "AGENTS.md", "statement": "s", "stop_code": "none"}}},
            "a trigger that is no practice": {"triggers": ["no-such-practice"]},
        }
        for name, bad in broken.items():
            with self.subTest(name):
                self.assertEqual(len(claim_registry.registry_problems(bad, ROOT)), 1, claim_registry.registry_problems(bad, ROOT))
        self.assertEqual(claim_registry.registry_problems({"duties": {"lead": ["a"]}, "stops": {"s": "ask"}, "gates": {}}, ROOT), [])

    def test_every_registered_claim_is_required_and_every_gap_is_a_required_claim(self):
        required = set(claims.required_claims(FILE))
        self.assertLessEqual(set(claim_registry.registry_claims(FILE)), required)
        self.assertLessEqual(set(FILE["known_gaps"]), required, "a known gap names a claim nothing requires: it is closed, or misspelled")

    def test_the_gates_are_the_asks_where_a_person_decides(self):
        self.assertEqual(sorted(FILE["gates"].values()), ["deploy.run", "intent.approve", "pr.merge", "product_scope.approve", "spec.approve"])

    def test_a_stop_code_no_claim_reaches_is_a_gap_and_a_claim_that_reaches_it_closes_it(self):
        self.assertEqual(claim_registry.uncovered_stop_codes(FILE), ["retries", "untestable", "waiting", "blocked"])
        for code in claim_registry.uncovered_stop_codes(FILE):
            self.assertIn(f"stop_code:{code}", FILE["known_gaps"])
        reached = dict(FILE, stops=dict(FILE["stops"], **{"gives-up": "retries"}))
        self.assertNotIn("retries", claim_registry.uncovered_stop_codes(reached))
        self.assertNotIn("stop_code:retries", claims.required_claims(reached))

    def test_a_routing_case_expects_the_route_its_claim_names(self):
        """A claim name that says minor on a case that expects normal was the defect in `route:minor-profiler`."""
        for sc in evals.load_scenarios(ROOT / "evals" / "routing"):
            for claim in [sc["claim"]] if isinstance(sc["claim"], str) else sc["claim"]:
                name = claim.removeprefix("route:")
                if claim.startswith("route:") and name in FILE["routes"]:
                    with self.subTest(sc["id"]):
                        self.assertEqual(sc["expected"]["route"], FILE["routes"][name])


if __name__ == "__main__":
    unittest.main()
