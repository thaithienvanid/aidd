"""The steps each route runs have one owner, `graph.routes` in schemas/roles.json, and an answer names a route, never a lane.

The method's table of routes is generated from the steps, a role and a flow name the routes they work on, and an answer of
`aidd risk` holds no `lane`. tests/fixtures/start-answers/risk-answers.json holds a digest of the whole answer for each
request of routes.json, so a later reading can only say what it said, and no route, ask, or reason moves unseen. Rebuild that
file only on purpose, with the reason in the commit: `python3 tests/test_route_steps.py` prints the digests the code in `src/` gives."""

import hashlib
import json
import sys
import unittest

import control_tables
from helpers import ROOT, run_cli

from aidd import config, knowledge, risk
from aidd.docsgen import generate
from aidd.kernel import json_schema, resources

DIGESTS = ROOT / "tests" / "fixtures" / "start-answers" / "risk-answers.json"
LOOP = knowledge.roles()["graph"]


def digests() -> dict[str, str]:
    """A digest of the whole `aidd risk --paths` answer for each request of control_tables.route_cases()."""
    found = {}
    for key, (profile, paths, change_type) in control_tables.route_cases().items():
        cfg = config.load_text(f'aidd_version: "1.0.0"\nprofile: {profile}\nowners:\n  approvers: ["@x"]\n')
        answer = risk.advice(cfg, paths, change_type=change_type)
        found[key] = hashlib.sha256(json.dumps(answer, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return found


class TheStepsOfARoute(unittest.TestCase):
    def test_every_route_names_steps_and_a_normal_and_a_major_change_run_the_same(self):
        self.assertEqual(list(LOOP["routes"]), list(config.ROUTES), "one entry for each route, in the route order")
        steps = set(LOOP["steps"])
        for route, text in LOOP["routes"].items():
            with self.subTest(route):
                named = [part.strip() for part in text.replace("⟲", "→").split("→")]
                self.assertTrue(set(named) <= steps | {"Spec approval", "Merge approval"}, named)
                self.assertIn("Implement", named)
        self.assertEqual(LOOP["routes"]["normal"], LOOP["routes"]["major"], "a major route adds documents, never steps")

    def test_the_routes_that_write_a_spec_first_are_the_ones_whose_steps_start_with_specify(self):
        first = tuple(route for route, text in LOOP["routes"].items() if text.startswith("Specify → Spec approval →"))
        self.assertEqual(first, config.SPEC_FIRST_ROUTES)
        for route in set(config.ROUTES) - set(first):
            self.assertNotIn("Specify", LOOP["routes"][route])

    def test_an_emergency_is_reviewed_before_the_merge_and_learns_last(self):
        steps = LOOP["routes"]["emergency"].split(" → ")
        self.assertLess(steps.index("Review"), steps.index("Merge approval"))
        self.assertLess(steps.index("Merge approval"), steps.index("Merge"))
        self.assertEqual(steps[-1], "Learn")
        meaning = resources.load_json("common.schema.json")["$defs"]["route"]["x-meanings"]["emergency"]
        self.assertIn("the review comes before the merge", meaning)
        self.assertNotIn("the Spec and the review follow", meaning)

    def test_the_method_holds_the_generated_table_of_steps(self):
        table = generate.render("roles:routes")
        self.assertIn(table, (ROOT / "docs" / "METHOD.md").read_text(encoding="utf-8"))
        for route, text in LOOP["routes"].items():
            with self.subTest(route):
                row = next(r for r in table.splitlines() if text in r)
                self.assertIn(route, row.split("|")[2])
                self.assertIn(config.route_words()[route], row.split("|")[1])

    def test_each_route_reads_as_one_word_and_each_role_and_flow_names_routes_of_the_loop(self):
        words = resources.load_json("common.schema.json")["$defs"]["route"]["x-words"]
        self.assertEqual(list(words), list(config.ROUTES))
        self.assertEqual(config.route_words(), words)
        for holder in [*LOOP["flows"], *knowledge.roles()["roles"].values()]:
            self.assertTrue(holder["routes"] and set(holder["routes"]) <= set(config.ROUTES), holder)
            self.assertEqual(holder["routes"], sorted(holder["routes"], key=config.ROUTES.index), "in the route order")

    def test_a_role_reads_its_routes_as_each_word_once(self):
        roles = knowledge.roles()["roles"]
        for name, role in roles.items():
            with self.subTest(name):
                said = knowledge.role_loop(role)
                words = [config.route_words()[r] for r in role["routes"]]
                self.assertEqual(said, f"{', '.join(role['steps'])} ({', '.join(dict.fromkeys(words))})")
                self.assertEqual(said.count("Spec first"), int("Spec first" in words))
        self.assertEqual(knowledge.role_loop(roles["developer"]), "Implement (no Spec, Spec first, repair first)")


class TheLaneIsGone(unittest.TestCase):
    def test_no_answer_of_aidd_risk_or_aidd_explain_has_a_lane(self):
        for paths in (["README.md"], ["src/payments/charge.py"], ["x/crypto/y"]):
            with self.subTest(paths):
                code, out = run_cli("risk", "--paths", *paths, "--json")
                answer = json.loads(out)
                self.assertEqual((code, json_schema.validate(answer, "risk.schema.json"), "lane" in answer), (0, [], False))
        schema = resources.load_json("risk.schema.json")["$defs"]["paths"]
        self.assertNotIn("lane", schema["properties"])
        self.assertNotIn("lane", schema["required"])
        self.assertNotIn("lane", resources.load_json("explain.schema.json")["$defs"]["type"]["enum"])
        self.assertNotIn("lane", knowledge.EXPLAIN_TYPES)

    def test_lane_is_no_word_aidd_knows_and_the_routes_are(self):
        code, out = run_cli("explain", "lane")
        self.assertEqual(code, 2)
        self.assertNotIn("was retired", out)
        code, out = run_cli("explain", "lane", "--json")
        answer = json.loads(out.split("\naidd explain:")[0])
        self.assertEqual((code, answer["matches"], answer["error"]["code"]), (2, [], "cli.unknown_word"))
        code, out = run_cli("explain", "route")
        self.assertEqual(code, 0)
        for route in config.ROUTES:
            code, out = run_cli("explain", route)
            self.assertEqual(code, 0)
            self.assertIn(f"Its steps: {LOOP['routes'][route]}.", out)

    def test_the_whole_answer_of_each_request_is_the_one_the_fixture_holds(self):
        then, now = json.loads(DIGESTS.read_text(encoding="utf-8")), digests()
        self.assertEqual(sorted(now), sorted(then), "the table and its digests are one set")
        self.assertEqual([k for k in now if now[k] != then[k]], [], "the whole answer is what the fixture holds")


if __name__ == "__main__":
    if sys.argv[1:] == []:
        json.dump(digests(), sys.stdout, indent=1, sort_keys=True)
        sys.stdout.write("\n")
    else:
        unittest.main()
