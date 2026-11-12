"""The `spec.approve` risk rules are the one owner of whether an agent asks for Spec approval on a route: the profiles
hold no route list of their own. These tables are the behavior before the rules took it over, so a cell that loosens
fails here, and the harness ask rules stay as strict in every harness."""

from __future__ import annotations

import contextlib
import copy
import itertools
import json
import tempfile
import unittest
from pathlib import Path

import helpers

from aidd import config, risk
from aidd.kernel import json_schema
from aidd.risk import harness_rules
from aidd.config import loading
from aidd.risk import routes

ROUTES = ("minor", "normal", "major", "emergency")
# A path for each route the paths can give: the emergency route is declared, never read from paths.
PATH_OF = {"minor": "src/app.py", "normal": ".github/workflows/ci.yml", "major": "src/billing/charge.py"}
# (profile, route) -> the level before the rules took it over. No config reads as solo.
BEFORE = {
    ("none", "minor"): "allow",
    ("none", "normal"): "report",
    ("none", "major"): "ask",
    ("none", "emergency"): "allow",
    ("solo", "minor"): "allow",
    ("solo", "normal"): "report",
    ("solo", "major"): "ask",
    ("solo", "emergency"): "allow",
    ("team", "minor"): "allow",
    ("team", "normal"): "ask",
    ("team", "major"): "ask",
    ("team", "emergency"): "allow",
}


def cfg(profile: str, extra: str = "") -> config.Config | None:
    return None if profile == "none" else config.load_text(f'aidd_version: "1.0.0"\nprofile: {profile}\n' + extra)


class EveryCellIsAsStrictAsBefore(unittest.TestCase):
    def test_each_profile_on_each_route(self):
        for (profile, route), want in BEFORE.items():
            with self.subTest(profile=profile, route=route):
                self.assertEqual(routes.spec_approval_level(cfg(profile), route), want)

    def test_a_config_rule_for_every_route_decides_every_route(self):
        # Before: a config `spec.approve` rule set both routes, whatever the profile said.
        for level in ("ask", "report", "allow"):
            for profile in ("solo", "team"):
                c = cfg(profile, f"risks:\n  rules:\n    - {{action: spec.approve, level: {level}}}\n")
                for route in ("normal", "major"):
                    with self.subTest(level=level, profile=profile, route=route):
                        self.assertEqual(routes.spec_approval_level(c, route), level)

    def test_a_rule_for_other_actions_or_narrowed_otherwise_leaves_the_cells(self):
        for rule in ("{action: 'spec.*', level: allow}", "{action: '*', level: allow}", "{action: spec.approve, role: developer, level: allow}"):
            for profile in ("solo", "team"):
                c = cfg(profile, f"risks:\n  rules:\n    - {rule}\n")
                for route in ROUTES:
                    with self.subTest(rule=rule, profile=profile, route=route):
                        self.assertEqual(routes.spec_approval_level(c, route), BEFORE[(profile, route)])

    def test_a_rule_for_one_route_changes_that_route_only(self):
        c = cfg("solo", "risks:\n  rules:\n    - {action: spec.approve, route: normal, level: ask}\n")
        self.assertEqual([routes.spec_approval_level(c, r) for r in ROUTES], ["allow", "ask", "ask", "allow"])
        c = cfg("team", "risks:\n  rules:\n    - {action: spec.approve, route: normal, level: report}\n")
        self.assertEqual([routes.spec_approval_level(c, r) for r in ROUTES], ["allow", "report", "ask", "allow"])

    def test_a_route_rule_cannot_lower_what_a_parent_locked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "preset.yaml").write_text(
                'aidd_version: "1.0.0"\nprofile: solo\nrisks:\n  rules:\n    - {action: spec.approve, level: ask, locked: true}\n'
            )
            (root / ".aidd").mkdir()
            (root / ".aidd" / "config.yaml").write_text(
                'aidd_version: "1.0.0"\nprofile: solo\nextends: [{path: preset.yaml}]\n'
                "risks:\n  rules:\n    - {action: spec.approve, route: normal, level: report}\n"
            )
            c = config.load_file(config.CONFIG_PATH, tmp)
        self.assertEqual([routes.spec_approval_level(c, r) for r in ("normal", "major")], ["ask", "ask"])

    def test_a_child_rule_for_every_route_replaces_a_parents_rule_for_one(self):
        # A preset that lowers the normal route, and a child that asks on every route: the child's ask holds.
        lower = "risks:\n  rules:\n    - {action: spec.approve, route: normal, level: report}\n"
        ask = "risks:\n  rules:\n    - {action: spec.approve, level: ask}\n"
        head = 'aidd_version: "1.0.0"\nprofile: team\n'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "grand.yaml").write_text(head + lower)
            (root / "preset.yaml").write_text(head + "extends: [{path: grand.yaml}]\n")
            (root / ".aidd").mkdir()
            (root / ".aidd" / "config.yaml").write_text(head + "extends: [{path: preset.yaml}]\n" + ask)
            chain = config.load_file(config.CONFIG_PATH, tmp)
            (root / ".aidd" / "config.yaml").write_text(head + "extends: [{path: grand.yaml}]\n" + ask)
            direct = config.load_file(config.CONFIG_PATH, tmp)
        org = config.load_text(head + ask, root_preset=head + lower)
        for name, c in (("a parent", direct), ("a grandparent", chain), ("the org preset", org)):
            with self.subTest(lowered_by=name):
                self.assertEqual([routes.spec_approval_level(c, r) for r in ("normal", "major")], ["ask", "ask"])

    def test_the_child_keeps_its_own_route_rules_whatever_their_order(self):
        both = (
            "risks:\n  rules:\n    - {action: spec.approve, route: normal, level: report}\n    - {action: spec.approve, level: ask}\n",
            "risks:\n  rules:\n    - {action: spec.approve, level: ask}\n    - {action: spec.approve, route: normal, level: report}\n",
        )
        other = 'aidd_version: "1.0.0"\nprofile: solo\nrisks:\n  rules:\n    - {action: pr.open, level: allow}\n'  # a parent that holds no Spec rule
        for text in both:
            for profile in ("solo", "team"):
                for parent in (None, other):
                    with self.subTest(order=text.splitlines()[2][:40], profile=profile, parent=bool(parent)):
                        c = config.load_text(f'aidd_version: "1.0.0"\nprofile: {profile}\n' + text, root_preset=parent)
                        self.assertEqual([routes.spec_approval_level(c, r) for r in ("normal", "major")], ["report", "ask"])

    def test_a_parent_rule_the_child_restates_gives_one_level_in_either_order(self):
        # The parent asks on the normal route, and the child restates it and also sets a rule for every route.
        parent = 'aidd_version: "1.0.0"\nprofile: team\nrisks:\n  rules:\n    - {action: spec.approve, route: normal, level: ask}\n'
        restate = "{action: spec.approve, route: normal, level: ask}"
        every = "{action: spec.approve, level: report}"
        levels = []
        for order in ((restate, every), (every, restate)):
            c = config.load_text('aidd_version: "1.0.0"\nprofile: team\nrisks:\n  rules:\n' + "".join(f"    - {r}\n" for r in order), root_preset=parent)
            levels.append([routes.spec_approval_level(c, r) for r in ("normal", "major")])
        self.assertEqual(levels, [["ask", "report"], ["ask", "report"]])

    def test_the_merged_levels_never_depend_on_the_order_of_a_childs_rules(self):
        every_kind = [
            {"action": "spec.approve", "level": lv, **({"route": rt} if rt else {})} for lv in ("ask", "report", "allow") for rt in (None, "normal", "major")
        ]
        parents = [[]] + [[r | {"locked": lock}] for r in every_kind for lock in (False, True)]
        for parent in parents:
            for first, second in itertools.combinations(every_kind, 2):
                if (first.get("route"), first["action"]) == (second.get("route"), second["action"]):
                    continue  # the same selector twice: the later rule rightly wins
                seen = set()
                for order in ((first, second), (second, first)):
                    merged = loading.merge_risks({"rules": copy.deepcopy(parent)}, {"rules": copy.deepcopy(list(order))}, "test", [])
                    c = config.Config({"risks": merged}, "solo")
                    seen.add(tuple(routes.spec_approval_level(c, r) for r in ("normal", "major")))
                self.assertEqual(len(seen), 1, f"parent {parent}, child {first} and {second}: {seen}")

    def test_a_child_route_rule_a_parents_lock_sets_aside_is_named(self):
        locked = 'aidd_version: "1.0.0"\nprofile: team\nrisks:\n  rules:\n    - {action: spec.approve, level: ask, locked: true}\n'
        c = config.load_text(
            'aidd_version: "1.0.0"\nprofile: solo\nrisks:\n  rules:\n    - {action: spec.approve, route: normal, level: report}\n', root_preset=locked
        )
        self.assertTrue(any("set aside" in w and "locked" in w for w in c.warnings), c.warnings)
        self.assertEqual(routes.spec_approval_level(c, "normal"), "ask")
        self.assertTrue(any("set aside" in w for w in risk.rule_set(c).ignored), "`aidd risk` shows it")

    def test_a_parents_lock_for_one_route_is_a_floor_for_that_route_only(self):
        """A lock raises and never lowers: a parent's locked `report` on the normal route lowers neither the built-in ask nor
        a child's ask, and a locked `ask` there raises a child's `report` (this test once pinned the lock lowering the ask)."""
        child = 'aidd_version: "1.0.0"\nprofile: team\nrisks:\n  rules:\n    - {action: spec.approve, level: %s}\n'
        for lock_level, child_level, want in (("report", "ask", ["ask", "ask"]), ("ask", "report", ["ask", "report"]), ("ask", "ask", ["ask", "ask"])):
            locked = (
                f'aidd_version: "1.0.0"\nprofile: team\nrisks:\n  rules:\n    - {{action: spec.approve, route: normal, level: {lock_level}, locked: true}}\n'
            )
            c = config.load_text(child % child_level, root_preset=locked)
            with self.subTest(lock=lock_level, child=child_level):
                self.assertEqual([routes.spec_approval_level(c, r) for r in ("normal", "major")], want)

    def test_the_data_lowers_one_cell_and_only_in_solo(self):
        # Never looser: the built-in rules ask on every route, and the one cell below ask is the solo profile's normal route.
        built_in = [r for r in risk.rule_set(None).rules if r.action == "spec.approve" and r.source == "built-in"]
        self.assertEqual([(r.route, r.level) for r in built_in], [(None, "ask")])
        profiles = config.profiles()["profiles"]
        self.assertEqual([(r["action"], r["route"], r["level"]) for r in profiles["solo"]["rules"]], [("spec.approve", "normal", "report")])
        self.assertEqual(profiles["team"]["rules"], [])
        self.assertEqual([r.source for r in risk.rule_set(None).rules if r.route], ["profile solo"], "with no config, solo applies")


class OneOwner(unittest.TestCase):
    def test_a_profile_holds_no_route_list(self):
        for name, profile in config.profiles()["profiles"].items():
            self.assertNotIn("spec_approval_routes", profile, name)

    def test_the_route_advice_reads_the_rule_for_that_route(self):
        for profile in ("none", "solo", "team"):
            c = cfg(profile)
            rs = risk.rule_set(c)
            for route, path in PATH_OF.items():
                with self.subTest(profile=profile, route=route):
                    answer = risk.advice(c, [path])
                    self.assertEqual(answer["route"], route)
                    want = "allow" if route == "minor" else risk.level_of(rs, "spec.approve", route=route)[0]
                    self.assertEqual(answer["spec_approval"], want)

    def test_the_profiles_table_is_read_from_the_rules(self):
        self.assertEqual(risk.routes_asking_for_spec_approval("solo"), ["major"])
        self.assertEqual(risk.routes_asking_for_spec_approval("team"), ["normal", "major"])

    def test_explain_says_when_each_profile_asks(self):
        for profile, want in (("solo", "asks for Spec approval on major;"), ("team", "asks for Spec approval on normal and major;")):
            code, out = helpers.run_cli("explain", profile)
            self.assertEqual(code, 0, out)
            self.assertIn(want, out, profile)

    def test_the_action_check_names_the_level_on_each_route(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.chdir(tmp):
            helpers.git(tmp, "init", "-q", "-b", "main")
            (Path(tmp) / ".aidd").mkdir()
            (Path(tmp) / ".aidd" / "config.yaml").write_text('aidd_version: "1.0.0"\nprofile: solo\n')

            def ask(*argv: str) -> dict:
                code, out = helpers.run_cli("risk", *argv, "--json")
                self.assertEqual(code, 0, out)
                return json.loads(out)

            plain = ask("--action", "spec.approve")
            self.assertEqual(plain["level"], "ask", "with no route it is the rule for every route")
            self.assertTrue(any("--route normal" in n and "report" in n for n in plain["notes"]), plain["notes"])
            self.assertEqual(ask("--action", "spec.approve", "--route", "normal")["level"], "report")
            self.assertEqual(ask("--action", "spec.approve", "--route", "major")["level"], "ask")
            on_paths = ask("--paths", PATH_OF["normal"])
            self.assertEqual(on_paths["spec_approval"], ask("--action", "spec.approve", "--route", on_paths["route"])["level"])
            listed = [r for r in ask("--list")["rules"] if r["action"] == "spec.approve"]
            self.assertEqual(sorted((r.get("route"), r["level"]) for r in listed if r.get("route")), [("normal", "report")])

    def test_a_route_belongs_to_spec_approve_alone(self):
        def errors(rule: dict) -> list[str]:
            return json_schema.validate(rule, "risks.schema.json#/$defs/rule")

        self.assertEqual(errors({"action": "spec.approve", "route": "normal", "level": "ask"}), [])
        self.assertTrue(errors({"action": "pr.merge", "route": "normal", "level": "ask"}), "a route on another action would never match, so it is an error")
        self.assertTrue(errors({"action": "spec.approve", "route": "minor", "level": "ask"}), "a route with no Spec has nothing to approve")
        with self.assertRaises(config.ConfigError) as refused:
            config.load_text('aidd_version: "1.0.0"\nprofile: solo\nrisks:\n  rules:\n    - {action: pr.merge, route: normal, level: ask}\n')
        self.assertIn("remove `route`", str(refused.exception))

    def test_an_environment_belongs_to_deploy_run_alone(self):
        """A selector only one action takes is an error on another, and the message names the action it needs."""
        base = 'aidd_version: "1.0.0"\nprofile: solo\nrisks:\n  rules:\n    - '
        wrong = {
            "an environment on a push": ({"action": "git.push", "environment": "dev"}, "environment", "deploy.run"),
            "a shared mark on a push": ({"action": "git.push", "environment_shared": False}, "environment_shared", "deploy.run"),
            "an environment on every action": ({"action": "*", "environment": "dev"}, "environment", "deploy.run"),
            "a route on a merge": ({"action": "pr.merge", "route": "normal"}, "route", "spec.approve"),
        }
        for name, (rule, key, action) in wrong.items():
            rule = rule | {"level": "ask"}
            with self.subTest(name):
                self.assertTrue(json_schema.validate(rule, "risks.schema.json#/$defs/rule"), "the schema refuses it too")
                with self.assertRaises(config.ConfigError) as refused:
                    config.load_text(base + json.dumps(rule) + "\n")
                self.assertIn(f"only `{action}` takes", str(refused.exception))
                self.assertIn(f"`{key}`", str(refused.exception))
        # A prefix or `*` that covers the action is told only to name it: removing the selector would widen the rule.
        covered = {
            "a locked prefix": ({"action": "deploy.*", "environment_shared": False, "locked": True}, "environment_shared", "deploy.run"),
            "every action, with an environment": ({"action": "*", "environment": "dev"}, "environment", "deploy.run"),
            "a spec prefix, with a route": ({"action": "spec.*", "route": "normal"}, "route", "spec.approve"),
            "every action, with a route": ({"action": "*", "route": "major"}, "route", "spec.approve"),
        }
        for name, (rule, key, action) in covered.items():
            with self.subTest(name), self.assertRaises(config.ConfigError) as refused:
                config.load_text(base + json.dumps(rule | {"level": "ask"}) + "\n")
            self.assertIn(f"set its action to `{action}`", str(refused.exception))
            self.assertNotIn(f"remove `{key}`", str(refused.exception))
        for rule in ({"action": "deploy.run", "environment": "dev"}, {"action": "deploy.run", "environment_shared": False}):
            self.assertEqual(json_schema.validate(rule | {"level": "ask"}, "risks.schema.json#/$defs/rule"), [], rule)

    def test_a_route_flag_belongs_to_the_spec_approval_check(self):
        code, out = helpers.run_cli("risk", "--action", "pr.merge", "--route", "normal")
        self.assertNotEqual(code, 0)
        self.assertIn("--route narrows `--action spec.approve` only", out)


class TheHarnessAskRulesStayAsStrict(unittest.TestCase):
    """A route rule has no command form: no harness ask rule may change with it, in any harness."""

    def test_each_harness_writes_the_same_entries_with_and_without_a_route_rule(self):
        def written(profile: str, extra: str, fmt: str) -> dict[str, str]:
            with tempfile.TemporaryDirectory() as tmp:
                rs = risk.rule_set(cfg(profile, extra))
                harness_rules.apply_harness_rules(Path(tmp), fmt, harness_rules.harness_patterns(rs, ["main"]), read_paths=harness_rules.harness_read_paths(rs))
                return {str(p.relative_to(tmp)): p.read_text() for p in sorted(Path(tmp).rglob("*")) if p.is_file()}

        raise_route = "risks:\n  rules:\n    - {action: spec.approve, route: major, level: ask}\n"
        for fmt in harness_rules.FORMATS:
            for profile in ("solo", "team"):
                with self.subTest(harness=fmt, profile=profile):
                    self.assertEqual(written(profile, raise_route, fmt), written(profile, "", fmt))
                    self.assertTrue(written(profile, "", fmt), "the harness holds ask rules at all")

    def test_the_patterns_are_those_of_the_built_in_rules_in_every_profile(self):
        base = harness_rules.harness_patterns(risk.rule_set(None), ["main"])
        for profile in ("solo", "team"):
            self.assertEqual(harness_rules.harness_patterns(risk.rule_set(cfg(profile)), ["main"]), base, profile)


if __name__ == "__main__":
    unittest.main()
