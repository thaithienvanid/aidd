"""Your own environment under a delegation: a deploy to an environment marked `shared: false` and named with no wildcard
stays `report`, because nobody else uses it. Every other deploy still asks. Each case below is one guard of that single
cell, so a guard removed makes one fail (the seeded faults are listed in the commit that adds this file)."""

import copy
import tempfile
import unittest
from unittest import mock

import helpers
from test_delegation_data import block, load

from aidd import risk
from aidd.kernel import json_schema, resources
from aidd.risk import harness_rules

OWN = "environments:\n  - {name: dev, branches: [dev], shared: false}\n"
SHARED = "environments:\n  - {name: production, branches: [main]}\n"
ENVS = "environments:\n  - {name: dev, branches: [dev], shared: false}\n  - {name: production, branches: [prod], shared: true}\n"


def level(extra: str, **narrow) -> str:
    return risk.level_of(risk.rule_set(load(extra + block())), "deploy.run", **narrow)[0]


def push_level(root: str, extra: str, push: str) -> str:
    return risk.command_level(risk.rule_set(load(extra + block())), f"git push {push}", cwd=root)["level"]


class OwnEnvironmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = cls.tmp.name
        helpers.git(cls.root, "init", "-q", "-b", "main")
        helpers.git(cls.root, "commit", "-q", "--allow-empty", "-m", "base")
        helpers.git(cls.root, "switch", "-qc", "feat")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_a_deploy_reads_by_the_environment_it_reaches(self):
        """Only the named, exact, `shared: false` environment keeps `report`; a shared one, an unmarked one, one the config does not hold,
        and a deploy that names none all ask."""
        cases = {
            "your own, named exactly": (OWN, {"environment": "dev"}, "report"),
            "your own, beside a shared one": (ENVS, {"environment": "dev"}, "report"),
            "a shared one": (ENVS, {"environment": "production"}, "ask"),
            "one the config marks nothing for": (SHARED, {"environment": "production"}, "ask"),
            "one the config does not hold": (OWN, {"environment": "elsewhere"}, "ask"),
            "no environment named, such as `fly deploy`": (OWN, {}, "ask"),
        }
        for name, (extra, narrow, want) in cases.items():
            with self.subTest(name):
                self.assertEqual(level(extra, **narrow), want)

    def test_a_wildcard_in_an_own_environment_makes_it_ask(self):
        """A glob can match other people's branches and tags, so the environment no longer reads as the developer's own."""
        cases = {
            "a branch glob": "{name: dev, branches: ['dev/*'], shared: false}",
            "a branch glob with a question mark": "{name: dev, branches: ['dev?'], shared: false}",
            "a tag glob": "{name: dev, tags: ['dev-*'], shared: false}",
            "one wildcard among exact names": "{name: dev, branches: [dev, 'try/*'], shared: false}",
        }
        for name, env in cases.items():
            with self.subTest(name):
                self.assertEqual(level(f"environments:\n  - {env}\n", environment="dev"), "ask")
        exact = "environments:\n  - {name: dev, branches: [dev], tags: [dev-1], shared: false}\n"
        self.assertEqual(level(exact, environment="dev"), "report")

    def test_a_config_rule_lowers_no_deploy_but_your_own_environments_cell(self):
        """The cell is the built-in rule for a deploy to your own environment. A config rule for every deploy, for every shared
        environment, or for one environment by name keeps no lower level, and a person's rule that asks for their own
        environment still asks."""
        cases = {
            "every deploy allowed": "risks:\n  rules:\n    - {action: deploy.run, level: allow}\n",
            "the shared environment by name": "risks:\n  rules:\n    - {action: deploy.run, environment: production, level: report}\n",
            "every shared environment": "risks:\n  rules:\n    - {action: deploy.run, environment_shared: true, level: allow}\n",
        }
        for name, rule in cases.items():
            with self.subTest(name):
                self.assertEqual(level(ENVS + rule, environment="production"), "ask")
                self.assertEqual(level(ENVS + rule, environment="dev"), "report")
        asks = "risks:\n  rules:\n    - {action: deploy.run, environment: dev, level: ask}\n"
        self.assertEqual(level(OWN + asks, environment="dev"), "ask", "a person's own rule for the environment is not set aside")
        own_asks = "risks:\n  rules:\n    - {action: deploy.run, environment_shared: false, level: allow}\n"
        self.assertEqual(level(OWN + own_asks, environment="dev"), "ask", "only the built-in rule is the cell; a rule the config writes for it is not")

    def test_only_the_rule_for_the_developers_own_environment_is_the_cell(self):
        """A built-in rule for the action that narrows to anything else rises with the rest."""
        data = copy.deepcopy(risk.builtin())
        data["rules"].append({"action": "deploy.run", "environment": "production", "level": "report", "reason": "a built-in rule for one name"})
        with mock.patch("aidd.risk.rules.builtin", return_value=data):
            self.assertEqual(level(ENVS, environment="production"), "ask")
            self.assertEqual(level(ENVS, environment="dev"), "report")

    def test_a_parents_lock_on_deploys_keeps_the_cell_asking(self):
        """A lock is a parent's word that deploys ask, so no cell stays under it, whatever the lock names."""
        for action in ("deploy.run", "deploy.*", "'*'"):
            with self.subTest(action):
                parent = f"risks:\n  rules:\n    - {{action: {action}, level: report, locked: true}}\n"
                delegated = risk.rule_set(load(OWN + block(), parent))
                self.assertEqual(risk.level_of(delegated, "deploy.run", environment="dev")[0], "ask")

    def test_no_other_action_keeps_its_level(self):
        """The data gives an exception to `deploy.run` alone, the built-in rule for your own environment."""
        data = resources.load_json("risks.json")["delegation"]
        self.assertEqual([i for i in data["rises_to_ask"] if isinstance(i, dict)], [{"action": "deploy.run", "except": [{"environment_shared": False}]}])
        for action in ("dependency.add", "migration.run.local"):
            self.assertEqual(risk.level_of(risk.rule_set(load(OWN + block())), action)[0], "ask")

    def test_an_item_of_the_rise_is_an_id_or_an_action_with_its_one_exception(self):
        """The exception is stated beside the rise it limits: `{action, except}` keeps the built-in rule a selector names,
        and a bare id keeps none, so the same deploys ask with no `except`."""
        rise = {
            "an id keeps no cell": ("deploy.run", "ask"),
            "an exception for your own environment": ({"action": "deploy.run", "except": [{"environment_shared": False}]}, "report"),
            "an exception for the shared ones": ({"action": "deploy.run", "except": [{"environment_shared": True}]}, "ask"),
        }
        for name, (item, want) in rise.items():
            data = copy.deepcopy(risk.builtin())
            data["delegation"]["rises_to_ask"] = [i for i in data["delegation"]["rises_to_ask"] if not (isinstance(i, dict) or i == "deploy.run")] + [item]
            with self.subTest(name), mock.patch("aidd.risk.rules.builtin", return_value=data):
                self.assertEqual(level(OWN, environment="dev"), want)

    def test_an_exception_names_a_selector_a_rule_has(self):
        """The schema allows `environment_shared` alone inside an `except` item, and an item with no `except` is an id."""
        for name, item, ok in (
            ("an id", "deploy.run", True),
            ("an exception", {"action": "deploy.run", "except": [{"environment_shared": False}]}, True),
            ("an unknown selector", {"action": "deploy.run", "except": [{"environment": "dev"}]}, False),
            ("an exception on another action", {"action": "git.push", "except": [{"environment_shared": False}]}, False),
            ("a selector with a typo", {"action": "deploy.run", "except": [{"environment_shred": False}]}, False),
            ("an empty exception", {"action": "deploy.run", "except": []}, False),
            ("an action with no exception", {"action": "deploy.run"}, False),
            ("an exception that is no list", {"action": "deploy.run", "except": {"environment_shared": False}}, False),
        ):
            with self.subTest(name):
                data = copy.deepcopy(risk.builtin())
                data["delegation"]["rises_to_ask"] = [item]
                problems = json_schema.validate(data, "risks.schema.json")
                self.assertEqual(not problems, ok, problems)

    def test_a_selector_the_schema_would_refuse_stops_the_rise_with_a_clear_error(self):
        """The data is checked by its schema, but the rise also checks the shape it reads, so a bad cell is a ValueError that
        names the selector, never an AttributeError."""
        for name, cell in {
            "empty": {},
            "another key": {"environment": "dev"},
            "an extra key": {"environment_shared": False, "x": 1},
            "no mapping": "dev",
        }.items():
            data = copy.deepcopy(risk.builtin())
            data["delegation"]["rises_to_ask"] = [{"action": "deploy.run", "except": [cell]}]
            with self.subTest(name), mock.patch("aidd.risk.rules.builtin", return_value=data), self.assertRaises(ValueError) as refused:
                level(OWN, environment="dev")
            self.assertIn("environment_shared", str(refused.exception))

    def test_without_a_delegation_nothing_changes(self):
        rs = risk.rule_set(load(OWN))
        self.assertEqual(risk.level_of(rs, "deploy.run", environment="dev")[0], "report")
        self.assertEqual(risk.level_of(rs, "deploy.run")[0], "ask")
        wild = risk.rule_set(load("environments:\n  - {name: dev, branches: ['dev/*'], shared: false}\n"))
        self.assertEqual(risk.level_of(wild, "deploy.run", environment="dev")[0], "report", "the reading without a delegation is as it was")

    def test_a_push_reads_the_same_way(self):
        cases = {
            "to your own environment's branch": (OWN, "origin dev", "report"),
            "to a shared environment's branch": (ENVS, "origin prod", "ask"),
            "to a ref a wildcard own environment matches": ("environments:\n  - {name: dev, branches: ['dev/*'], shared: false}\n", "origin dev/other", "ask"),
        }
        for name, (extra, push, want) in cases.items():
            with self.subTest(name):
                self.assertEqual(push_level(self.root, extra, push), want)

    def test_the_harness_asks_before_a_push_where_the_delegation_asks(self):
        """The ask rules a harness enforces follow the same levels: none for your own environment's branch, one for a shared
        environment's, and one for a wildcard own environment's."""

        def patterns(extra: str) -> list[str]:
            return harness_rules.harness_patterns(risk.rule_set(load(extra + block())), "main")

        self.assertFalse([p for p in patterns(OWN) if p.startswith("git push") and " dev" in p], "your own environment's branch asks nothing")
        self.assertTrue([p for p in patterns(ENVS) if p.startswith("git push * prod")])
        self.assertTrue([p for p in patterns("environments:\n  - {name: dev, branches: ['dev/*'], shared: false}\n") if "dev/*" in p])


if __name__ == "__main__":
    unittest.main()
