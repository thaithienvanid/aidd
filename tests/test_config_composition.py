"""Config composition: under `extends`, a child's effect is exactly the entries it names, and every lock reaches exactly
what it names. The rows come from `config.schema.json`, so a map or a group added to the schema is covered with no edit
here: every object merges member by member at every depth, a list or a scalar replaces, a lock on a key (`docs`) or on
one member (`docs.disabled`) keeps the parent's value, and a lock on a path the schema lacks fails with the closest
path."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts src/ on the path and makes the run hermetic)
from aidd import config
from aidd.config import loading
from aidd.kernel import resources

# Keys with a merge of their own (a rule for each is in the tests beside it): `project` binds by tightening, `risks`
# merges areas, actions, and rules by id, `standards_policy` adds and tightens, `delegation` only narrows, and the
# lists `standards` and `environments` merge by name, and `extends` and `locks` are not merged at all (OwnMergeMaps
# and EnvironmentsMergeByName hold their rows).
OWN_MERGE = {"project", "risks", "standards_policy", "delegation", "standards", "environments", "extends", "locks"}
# The maps under those keys: a new one fails the test below until a row for it is here.
OWN_MERGE_MAPS = {("risks", "areas"), ("risks", "actions"), ("standards_policy", "replace")}
# A policy only tightens, so a child cannot give an entry of its parent's another value.
KEEPS_THE_PARENTS_ENTRY = {("standards_policy", "replace")}
PARENT, CHILD = "from-parent", "from-child"


def deref(node: dict, base: str) -> tuple[dict, str]:
    while "$ref" in node:
        file, _, frag = node["$ref"].partition("#")
        base = resources.schema_file(file) if file else base
        node = resources.load_json(base)
        for part in frag.split("/")[1:]:
            node = node[part]
    return node, base


def objects(node: dict, base: str, path: tuple = (), found: list | None = None) -> list[tuple[tuple, list[str], str]]:
    """(path, two member names, kind) of every object under `node` that has at least two members: a keyed map or a
    group. A key of a keyed map is written `k`; a list ends the walk, because a list replaces."""
    found = [] if found is None else found
    node, base = deref(node, base)
    if node.get("type") != "object":
        return found
    extra = node.get("additionalProperties")
    if isinstance(extra, dict):
        found.append((path, ["a", "b"], "map"))
        objects(extra, base, (*path, "k"), found)
        return found
    props = node.get("properties", {})
    if len(props) >= 2:
        found.append((path, list(props)[:2], "group"))
    for name, sub in props.items():
        objects(sub, base, (*path, name), found)
    return found


def leaves(node: dict, base: str, path: tuple = (), found: list | None = None) -> list[tuple[tuple, bool]]:
    """(path, is a list) of every list and every single value under `node`, through groups and keyed maps."""
    found = [] if found is None else found
    node, base = deref(node, base)
    if node.get("type") != "object":
        found.append((path, node.get("type") == "array"))
        return found
    extra = node.get("additionalProperties")
    if isinstance(extra, dict):
        leaves(extra, base, (*path, "k"), found)
    for name, sub in node.get("properties", {}).items():
        leaves(sub, base, (*path, name), found)
    return found


def nest(path: tuple, value) -> dict:
    for key in reversed(path):
        value = {key: value}
    return value


def dig(tree: dict, path: tuple):
    for key in path:
        tree = tree[key]
    return tree


SCHEMA = resources.load_json("config.schema.json")
LOCKABLE = set(SCHEMA["properties"]["locks"]["items"]["anyOf"][0]["enum"])


def generic(path: tuple) -> bool:
    return bool(path) and path[0] not in OWN_MERGE


def merged(parent: dict, child: dict) -> tuple[dict, list[str]]:
    warnings: list[str] = []
    return loading.merge(parent, child, "child", warnings), warnings


class EveryGroupAndMapMergesByMember(unittest.TestCase):
    def test_rows_come_from_the_schema(self):
        rows = [o for o in objects(SCHEMA, "config.schema.json") if generic(o[0])]
        paths = {".".join(p) for p, _, _ in rows}
        # The maps this change is for are among them, and a schema with none would pass every row for nothing.
        self.assertTrue({"owners.specialists", "agents.models", "agents.effort", "development_teams", "docs.disabled"} <= paths, paths)

    def test_a_child_adds_a_member_and_overrides_one_it_names(self):
        for path, (a, b), kind in [o for o in objects(SCHEMA, "config.schema.json") if generic(o[0])]:
            with self.subTest(path=".".join(path), kind=kind):
                parent, child = nest(path, {a: PARENT}), nest(path, {b: CHILD})
                out, warnings = merged(parent, child)
                self.assertEqual(dig(out, path), {a: PARENT, b: CHILD})
                self.assertEqual(warnings, [])
                again, _ = merged(parent, nest(path, {a: CHILD}))
                self.assertEqual(dig(again, path), {a: CHILD})

    def test_a_list_or_a_single_value_replaces_whole(self):
        for path, is_list in [(p, kind) for p, kind in leaves(SCHEMA, "config.schema.json") if generic(p)]:
            with self.subTest(path=".".join(path), is_list=is_list):
                parent, child = ([PARENT, "x"], [CHILD]) if is_list else (PARENT, CHILD)
                out, _ = merged(nest(path, parent), nest(path, child))
                self.assertEqual(dig(out, path), child)

    def test_both_kinds_of_leaf_are_in_the_schema(self):
        kinds = {is_list for p, is_list in leaves(SCHEMA, "config.schema.json") if generic(p)}
        self.assertEqual(kinds, {True, False}, "a schema with no list, or no single value, would pass its row for nothing")

    def test_a_group_locked_by_name_keeps_the_parents_value(self):
        for path, (a, b), _ in [o for o in objects(SCHEMA, "config.schema.json") if generic(o[0]) and o[0][0] in LOCKABLE]:
            with self.subTest(path=".".join(path)):
                parent = {**nest(path, {a: PARENT}), "locks": [path[0]]}
                out, warnings = merged(parent, nest(path, {a: CHILD, b: CHILD}))
                self.assertEqual(dig(out, path), {a: PARENT})
                self.assertIn(f"{path[0]} is locked", " ".join(warnings))

    def test_a_dotted_lock_reaches_its_member_alone_and_beside_a_bare_one(self):
        for path, (a, b), _ in [o for o in objects(SCHEMA, "config.schema.json") if generic(o[0]) and o[0][0] in LOCKABLE]:
            with self.subTest(path=".".join(path)):
                dotted = ".".join((*path, a))
                parent = {**nest(path, {a: PARENT, b: PARENT}), "tests": [{"name": PARENT}], "locks": [dotted, "tests"]}
                child = {**nest(path, {a: CHILD, b: CHILD}), "tests": [{"name": CHILD}], "specs_dir": CHILD}
                out, warnings = merged(parent, child)
                self.assertEqual(dig(out, path), {a: PARENT, b: CHILD}, "the lock reaches the member it names, no sibling")
                self.assertEqual(out["tests"], [{"name": PARENT}], "the bare lock still reaches the whole group")
                self.assertEqual(out["specs_dir"], CHILD)
                self.assertIn(f"{dotted} is locked", " ".join(warnings))

    def test_the_maps_with_a_merge_of_their_own_are_the_ones_listed(self):
        own = {p for p, _, kind in objects(SCHEMA, "config.schema.json") if p and p[0] in OWN_MERGE and kind == "map" and len(p) == 2}
        self.assertEqual(own, OWN_MERGE_MAPS, "a new keyed map under a key with its own merge needs a row in OwnMergeMaps")


class EveryLockableKeySaysWhatItsLockMeans(unittest.TestCase):
    def test_a_lock_freezes_a_key_except_project_which_tightens(self):
        props = SCHEMA["properties"]
        for key in LOCKABLE:
            with self.subTest(key=key):
                node, _ = deref(props[key], "config.schema.json")
                text = props[key].get("description") or node.get("description", "")
                self.assertIn("tightens" if key == "project" else "freezes", text)
        for word in ("freezes", "tightens"):
            self.assertIn(word, props["locks"]["description"])


class OwnMergeMaps(unittest.TestCase):
    """The keyed maps under keys that merge their own way still keep what the parent set and add what the child names."""

    def test_each_map_adds_and_overrides_by_key(self):
        for path in sorted(OWN_MERGE_MAPS | {("project", "defaults", "disabled")}):
            with self.subTest(path=".".join(path)):
                out, _ = merged(nest(path, {"a": PARENT}), nest(path, {"b": CHILD}))
                self.assertEqual(dig(out, path), {"a": PARENT, "b": CHILD})
                again, _ = merged(nest(path, {"a": PARENT}), nest(path, {"a": CHILD}))
                self.assertEqual(dig(again, path), {"a": PARENT if path in KEEPS_THE_PARENTS_ENTRY else CHILD})

    def test_an_area_or_an_action_merges_by_member_too(self):
        for section in ("areas", "actions"):
            with self.subTest(section=section):
                out, _ = merged({"risks": {section: {"x": {"description": PARENT, "paths": [PARENT]}}}}, {"risks": {section: {"x": {"paths": [CHILD]}}}})
                self.assertEqual(out["risks"][section]["x"], {"description": PARENT, "paths": [CHILD]})

    def test_false_turns_an_entry_back_on_with_or_without_a_lock(self):
        for name, parent_locks in {"no lock": [], "a lock": ["docs.disabled"], "a bare lock": ["docs"]}.items():
            with self.subTest(name):
                parent = {"docs": {"disabled": {"runbook": PARENT, "authz-matrix": PARENT}}, "locks": parent_locks}
                out, warnings = merged(parent, {"docs": {"disabled": {"runbook": False, "tracking-plan": CHILD}}})
                self.assertNotIn("runbook", out["docs"]["disabled"])
                self.assertEqual(out["docs"]["disabled"]["authz-matrix"], PARENT, "a type the child does not name stays off")
                self.assertEqual("tracking-plan" in out["docs"]["disabled"], not parent_locks)


class EnvironmentsMergeByName(unittest.TestCase):
    PARENT_ENVS = [{"name": "production", "branches": ["main"]}, {"name": "staging", "branches": ["stage"]}]

    def test_a_child_adds_an_environment_or_overrides_one_and_removes_none(self):
        parent = {"environments": self.PARENT_ENVS}
        child = {"environments": [{"name": "staging", "branches": ["next"]}, {"name": "dev", "branches": ["dev"]}]}
        out, warnings = merged(parent, child)
        self.assertEqual([e["name"] for e in out["environments"]], ["production", "staging", "dev"])
        self.assertEqual(out["environments"][1]["branches"], ["next"])
        self.assertEqual(out["environments"][0], self.PARENT_ENVS[0])
        self.assertEqual(warnings, [])
        self.assertEqual(merged(parent, {"environments": []})[0]["environments"], self.PARENT_ENVS, "an empty list removes nothing")

    def test_a_lock_on_the_list_or_on_a_deploy_rule_keeps_the_parents_environment(self):
        child = {"environments": [{"name": "production", "branches": ["any"], "shared": False}, {"name": "dev", "branches": ["dev"]}]}
        rule = {"action": "deploy.run", "level": "ask", "environment": "production", "locked": True}
        for name, parent, kept in (
            ("a lock on environments", {"environments": self.PARENT_ENVS, "locks": ["environments"]}, ["production", "staging"]),
            ("a locked deploy rule", {"environments": self.PARENT_ENVS, "risks": {"rules": [rule]}}, ["production", "staging", "dev"]),
        ):
            with self.subTest(name):
                out, _ = merged(parent, child)
                self.assertEqual([e["name"] for e in out["environments"]], kept)
                self.assertEqual(out["environments"][0], self.PARENT_ENVS[0])


class ThreeLevelsOfExtends(unittest.TestCase):
    """Each level adds to what the levels above set, and a lock set at the top holds through every level below."""

    def test_the_chain_keeps_every_level_and_the_top_lock(self):
        top = 'aidd_version: "1.0.0"\nprofile: team\nlocks: [owners.specialists.security]\nowners:\n  specialists:\n    security: ["@top/sec"]\nagents:\n  models:\n    reasoning: anthropic/a\n'
        middle = 'aidd_version: "1.0.0"\nprofile: team\nextends: [{path: top.yaml}]\nowners:\n  specialists:\n    security: ["@mid/sec"]\n    privacy: ["@mid/priv"]\nagents:\n  models:\n    execution: anthropic/b\n'
        child = 'aidd_version: "1.0.0"\nprofile: team\nextends: [{path: middle.yaml}]\nowners:\n  specialists:\n    data: ["@me"]\n    security: ["@me/sec"]\nagents:\n  models:\n    verifier: anthropic/c\n'
        files = {"top.yaml": top, "middle.yaml": middle}
        cfg = config.load_text(child, read=files.get)
        self.assertEqual(cfg.get("owners", "specialists"), {"security": ["@top/sec"], "privacy": ["@mid/priv"], "data": ["@me"]})
        self.assertEqual(cfg.get("agents", "models"), {"reasoning": "anthropic/a", "execution": "anthropic/b", "verifier": "anthropic/c"})
        self.assertEqual(sum("owners.specialists.security is locked" in w for w in cfg.warnings), 2, cfg.warnings)


class InitFollowsALockedProfile(unittest.TestCase):
    """`aidd init` takes the profile from the merged config, so a child's `solo` under a locked `team` writes the ruleset `team` needs."""

    CHILD = 'aidd_version: "1.0.0"\nprofile: solo\nextends: [{path: org.yaml}]\n'
    PRESET = 'aidd_version: "1.0.0"\nprofile: team\nlocks: [profile]\n'

    def setup_repo(self, parent: str) -> Path:
        from init_plan_helpers import repo

        root = repo(parent)
        (root / ".aidd").mkdir()
        (root / ".aidd" / "config.yaml").write_text(self.CHILD, encoding="utf-8")
        (root / "org.yaml").write_text(self.PRESET, encoding="utf-8")
        return root

    def test_the_ruleset_follows_the_locked_profile(self):
        from helpers import aidd_here

        with tempfile.TemporaryDirectory() as d:
            root = self.setup_repo(d)
            result = aidd_here("init", "--ci", "github", "--harness", "none", cwd=root)
            self.assertEqual(result.returncode, 0, result.stderr)
            rules = {r["type"]: r for r in json.loads((root / ".github" / "rulesets" / "main.json").read_text())["rules"]}
            self.assertEqual(rules["pull_request"]["parameters"]["required_approving_review_count"], 1)

    def test_a_profile_flag_against_the_lock_is_refused_with_both_values_and_the_parent(self):
        from helpers import aidd_here

        with tempfile.TemporaryDirectory() as d:
            root = self.setup_repo(d)
            result = aidd_here("init", "--profile", "solo", "--ci", "github", "--harness", "none", cwd=root)
            self.assertEqual(result.returncode, 2)
            for word in ("--profile solo", "profile team", "org.yaml"):
                self.assertIn(word, result.stderr)
            self.assertFalse((root / ".github").exists(), "a refused run writes nothing")


class HeadlineCases(unittest.TestCase):
    """The cases an org preset depends on, loaded the way a repository loads them."""

    PRESET = (
        'aidd_version: "1.0.0"\nprofile: team\nlocks: [profile, owners.specialists.security]\n'
        "owners:\n  approvers: ['@org/leads']\n  specialists:\n    security: ['@org/sec']\n    privacy: ['@org/priv']\n"
        "agents:\n  models:\n    reasoning: anthropic/claude-opus-5-5\n    verifier: openai/gpt-5\n  effort:\n    reasoning: high\n"
    )

    def load(self, child_body: str) -> config.Config:
        text = 'aidd_version: "1.0.0"\nextends: [{path: preset.yaml}]\n' + ("" if child_body.startswith("profile") else "profile: team\n") + child_body
        return config.load_text(text, read=lambda _: self.PRESET)

    def test_a_child_that_adds_a_pool_and_a_model_keeps_the_presets(self):
        cfg = self.load(
            "owners:\n  specialists:\n    data: ['@me']\n    security: ['@me']\n    privacy: ['@me/priv']\n"
            "agents:\n  models:\n    execution: anthropic/claude-sonnet-5-5\n  effort:\n    execution: low\n"
        )
        self.assertEqual(cfg.get("owners", "specialists"), {"security": ["@org/sec"], "privacy": ["@me/priv"], "data": ["@me"]})
        self.assertEqual(cfg.get("owners", "approvers"), ["@org/leads"])
        self.assertEqual(
            cfg.get("agents", "models"),
            {"reasoning": "anthropic/claude-opus-5-5", "verifier": "openai/gpt-5", "execution": "anthropic/claude-sonnet-5-5"},
        )
        self.assertEqual(cfg.get("agents", "effort"), {"reasoning": "high", "execution": "low"})
        self.assertIn("owners.specialists.security is locked by a parent config", " ".join(cfg.warnings))

    def test_the_keys_the_config_names_still_load(self):
        cfg = self.load("specs_dir: work/specs\nproposals_dir: work/proposals\n")
        self.assertEqual((cfg.specs_dir, cfg.proposals_dir), ("work/specs", "work/proposals"))

    def test_a_child_cannot_switch_a_locked_profile(self):
        cfg = self.load("profile: solo\n")
        self.assertEqual((cfg.profile, cfg.get("profile")), ("team", "team"))
        self.assertIn("profile is locked by a parent config (preset.yaml) at 'team', so 'solo' is ignored", " ".join(cfg.warnings))
        self.assertEqual(self.load("profile: team\n").warnings, [])  # restating the locked value changes nothing


class MistypedLocks(unittest.TestCase):
    def fails(self, lock: str) -> str:
        with self.assertRaises(config.ConfigError) as caught:
            config.load_text(f'aidd_version: "1.0.0"\nprofile: solo\nlocks: [{lock}]\n')
        return str(caught.exception)

    def test_a_typo_names_the_closest_path(self):
        for lock, close in {
            "docs.disabeld": "docs.disabled",
            "owners.specialist": "owners.specialists",
            "owner": "owners",
            "agents.model": "agents.models",
        }.items():
            with self.subTest(lock=lock):
                message = self.fails(lock)
                self.assertIn(f"did you mean `{close}`", message)
                self.assertIn("line 3", message)

    def test_a_path_the_schema_cannot_lock_fails_with_the_reason(self):
        self.assertIn("a list", self.fails("tests.command"))
        self.assertIn("write `tests`.", self.fails("tests.command"))
        self.assertNotIn("preview.command", self.fails("tests.command"), "the guess agrees with the fix")
        self.assertIn("empty member name", self.fails("owners.specialists."))
        self.assertTrue(self.fails("docs.nope").splitlines()[-1].endswith("`docs.disabled`."))
        self.assertIn("project", self.fails("project.rules"))
        self.assertIn("not a key a parent can lock", self.fails("specs_dir.x"))

    def test_every_member_path_of_a_lockable_key_loads(self):
        for path, _, _ in [o for o in objects(SCHEMA, "config.schema.json") if o[0] and o[0][0] in LOCKABLE and o[0][0] != "project"]:
            with self.subTest(path=".".join(path)):
                config.load_text(f'aidd_version: "1.0.0"\nprofile: solo\nlocks: [{".".join(path)}]\n')


class TheEmptyConfig(unittest.TestCase):
    def test_it_reads_as_a_config_that_sets_nothing(self):
        """A caller with no config reads `(cfg or config.EMPTY)`, so it must answer as a loaded config with no setting does."""
        bare = config.load_text('aidd_version: "1.0.0"\nprofile: solo\n')
        for name in ("profile", "specs_dir", "proposals_dir", "docs_dir", "approvers", "tests", "docs_required", "max_runbook_age_days", "max_review_age_days"):
            with self.subTest(name):
                self.assertEqual(getattr(config.EMPTY, name), getattr(bare, name))


if __name__ == "__main__":
    unittest.main()
