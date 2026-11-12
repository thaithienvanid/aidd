"""The product scope's approval: the action a person answers, the area that keeps its files out of a delegated merge, the gate in
Plan, and the proof that adding them lowers no level and raises no route for any other path."""

from __future__ import annotations

import unittest

import helpers  # noqa: F401  # the hermetic environment
from helpers import ROOT, git

from aidd import config, knowledge, risk, workitems
from aidd.delegation import diff_signals, policy
from aidd.kernel import resources
from aidd.risk import rules

AREA = "product_scope"
# The five files a person's approval covers, under the product folder, in the order the area lists them.
FILES = ("brief.md", "brd.md", "prd.md", "outcomes.md", "intents/order.md")


def cfg(text: str = "") -> config.Config:
    return config.load_text('aidd_version: "1.0.0"\nprofile: solo\n' + text)


def areas_of(rs: risk.RuleSet, path: str) -> list[str]:
    return risk.areas_of(rs, path)


class TheActionTests(unittest.TestCase):
    def test_the_action_asks_under_every_profile_and_is_never_delegable(self):
        for profile in ("solo", "team"):
            with self.subTest(profile=profile):
                self.assertEqual(risk.level_of(risk.rule_set(config.Config({}, profile)), "product_scope.approve")[0], "ask")
        data = resources.load_json("risks.json")
        self.assertEqual(
            data["actions"]["product_scope.approve"]["commands"], data["actions"]["spec.approve"]["commands"], "it is held by the patterns of `aidd approve`"
        )
        self.assertNotIn("product_scope.approve", policy.delegable())
        self.assertNotIn("product_scope.approve", data["delegation"]["actions"])
        self.assertEqual(
            policy.covered({"decides": ["product_scope.approve", "spec.approve"]}), ["spec.approve"], "a config that names it decides nothing by it"
        )

    def test_nothing_new_is_delegable(self):
        self.assertEqual(policy.delegable(), ["spec.approve", "git.push", "git.merge", "pr.merge"])

    def test_the_gate_stands_in_plan_before_the_intent_approval_with_a_decision_right_of_its_own(self):
        loop = knowledge.roles()["graph"]
        gates = {g["name"]: g for g in loop["gates"]}
        self.assertEqual((gates["Product scope approval"]["stage"], gates["Product scope approval"]["actions"]), ("Plan", ["product_scope.approve"]))
        names = [g["name"] for g in loop["gates"]]
        self.assertLess(names.index("Product scope approval"), names.index("Intent approval"))
        rights = [d for d in loop["decision_rights"] if d.get("gate") == "Product scope approval"]
        self.assertEqual(len(rights), 1)
        self.assertIn("never covers it", rights[0]["decided_by"], "a delegation never decides it")

    def test_the_gate_is_found_by_its_step_and_a_note_never_names_it_as_the_next_role(self):
        """Each step code a gate's action gives is an approval a handoff note must not name as its next role."""
        from aidd.workitems import handoff_notes, step_reasons

        self.assertIn("Product scope approval", step_reasons.step_reason("product_scope.approve"))
        approvals = {a for g in knowledge.roles()["graph"]["gates"] for a in g["actions"] if a in workitems.STEP_CODES}
        self.assertEqual(sorted(approvals), sorted(handoff_notes.APPROVAL_STEPS))
        self.assertIn("product_scope.approve", approvals)

    def test_a_decision_point_is_never_suggested_lower_however_many_yeses(self):
        from aidd.risk import suggestions

        self.assertIn(("product_scope.approve", None, None), suggestions.DECISION_POINTS)


class TheAreaTests(unittest.TestCase):
    def test_the_area_holds_the_five_files_and_is_reserved_with_the_minor_route(self):
        data = resources.load_json("risks.json")
        area = data["areas"][AREA]
        self.assertEqual(area["paths"], [f"**/product/{name}" for name in FILES])
        self.assertEqual((area["route"], area["dimensions"], area.get("exclude")), ("minor", [], None))
        self.assertIn(AREA, data["delegation"]["reserved_areas"])
        self.assertEqual(rules.PRODUCT_SCOPE, AREA)

    def test_the_area_names_each_file_the_product_scope_types_name_and_the_brief_beside_them(self):
        """The registry of item types owns where each product scope file lives. The area holds those files and the brief, which has no row
        there yet, so a file added to a type, or a type renamed, fails here until the area follows."""
        rows = config.item_type_rows()
        owned = {file["path"].removeprefix("{product}/") for name in config.types_in("product_scope") for file in rows[name]["files"]}
        held = {p.removeprefix("**/product/") for p in resources.load_json("risks.json")["areas"][AREA]["paths"]}
        self.assertEqual(held - owned, {"brief.md"})
        self.assertEqual(owned - held, set())

    def test_each_file_is_in_the_area_wherever_the_product_folder_stands_and_an_intent_file_is_not(self):
        rs = risk.rule_set(None)
        cases = {
            **{f"product/{name}": [AREA] for name in FILES},
            **{f"packages/app/product/{name}": [AREA] for name in FILES},
            "product/intents/INTENT-1.md": [],  # each slice start edits it
            "product/intents/INTENT-1/decision-card.md": [],
            "product/notes.md": [],
            "product/intents/order.md.bak": [],
            "product/BRD.md": [AREA],  # a path is read without its case, as on macOS and Windows
            "docs/prd.md": [],
            "products/prd.md": [],
            "src/product.md": [],
        }
        for path, found in cases.items():
            with self.subTest(path=path):
                self.assertEqual(areas_of(rs, path), found)

    def test_a_change_to_one_is_minor_and_an_edit_is_allowed_as_before(self):
        rs = risk.rule_set(None)
        for name in FILES:
            with self.subTest(file=name):
                path = f"product/{name}"
                found = risk.route_for(rs, [path])
                self.assertEqual((found.route, list(found.areas)), ("minor", [AREA]))
                self.assertEqual(risk.edit_level(rs, [path])[0], "allow", "the person's yes is the approval, never a prompt for each edit")

    def test_the_config_s_product_dir_holds_the_same_files_and_the_default_adds_no_second_glob(self):
        built_in = resources.load_json("risks.json")["areas"][AREA]["paths"]
        cases = {
            # the config's lines, the folder they name, and whether `**/product/` already names it
            "": ("product", True),
            "product_dir: product\n": ("product", True),
            "product_dir: ./product/\n": ("product", True),
            "product_dir: docs/product\n": ("docs/product", True),
            "product_dir: plans\n": ("plans", False),
            "product_dir: ./plans/\n": ("plans", False),
            "product_dir: docs/scope\n": ("docs/scope", False),
        }
        for text, (folder, named) in cases.items():
            with self.subTest(text=text):
                rs = risk.rule_set(cfg(text))
                added = [] if named else [f"{folder}/{name}" for name in FILES]
                self.assertEqual(rs.areas[AREA]["paths"], [*built_in, *added])
                for name in FILES:
                    self.assertEqual(areas_of(rs, f"{folder}/{name}"), [AREA])
                    self.assertEqual(
                        diff_signals.reserved_scopes(rs, [f"{folder}/{name}"]), [f"{folder}/{name} ({AREA})"], "a scope that names the file reaches it"
                    )
                self.assertEqual(areas_of(rs, f"{folder}/intents/INTENT-1.md"), [])
        self.assertEqual(areas_of(risk.rule_set(None), "plans/prd.md"), [], "with no config the default folder alone holds it")

    def test_the_delegate_check_reads_the_area_as_reserved_for_every_file_in_every_folder(self):
        cases = {
            # the config's lines, then each path with whether a delegated change to it is a reserved path
            "": {
                "product/prd.md": True,
                "product/intents/order.md": True,
                "a/product/brief.md": True,
                "docs/product/prd.md": True,  # a false defer, accepted: any folder named `product` is held (SECURITY.md names both)
                "vendor/lib/product/brief.md": True,
                "product/intents/INTENT-1.md": False,
                "plans/prd.md": False,
            },
            "product_dir: plans\n": {
                "plans/prd.md": True,
                "plans/intents/order.md": True,
                "plans/brief.md": True,
                "product/outcomes.md": True,
                "plans/intents/INTENT-1.md": False,
            },
            "product_dir: docs/scope\n": {"docs/scope/brd.md": True, "docs/scope/notes.md": False, "docs/brd.md": False},
        }
        for text, paths in cases.items():
            rs = risk.rule_set(cfg(text))
            for path, reserved in paths.items():
                with self.subTest(config=text, path=path):
                    self.assertEqual(bool(diff_signals.reserved_paths(rs, [path])), reserved)

    def test_a_folder_that_is_the_top_or_odd_adds_no_path_that_reaches_every_file(self):
        built_in = resources.load_json("risks.json")["areas"][AREA]["paths"]
        for folder in (".", "./", "", "a[b", "a{b}"):
            with self.subTest(folder=folder):
                rs = risk.rule_set(config.Config({"product_dir": folder}, "solo"))
                self.assertEqual(rs.areas[AREA]["paths"][: len(built_in)], built_in)
                if folder in (".", "./", ""):
                    self.assertEqual(rs.areas[AREA]["paths"], built_in, "the repository's top adds no path")
                for path in ("src/app.py", "README.md", "brd.md", "prd.md", "product/intents/INTENT-1.md", "docs/guide.md"):
                    self.assertEqual(areas_of(rs, path), [], path)

    def test_a_config_that_redefines_the_area_keeps_the_five_files_reserved_in_the_folder_it_names(self):
        """A config or a preset that writes only an addition to the area, or an area of its own, un-reserves nothing."""
        redefined = {
            "an addition alone": "      paths: ['**/roadmap.md']\n",
            "a path that is no product folder": "      paths: [mine/**]\n",
            "the built-in globs and an addition": "      paths: ['**/product/prd.md', '**/roadmap.md']\n",
        }
        for name, paths in redefined.items():
            for folder in ("product", "plans", "docs/scope"):
                with self.subTest(name=name, product_dir=folder):
                    rs = risk.rule_set(cfg(f"product_dir: {folder}\nrisks:\n  areas:\n    product_scope:\n{paths}      route: normal\n"))
                    for file in FILES:
                        path = f"{folder}/{file}"
                        self.assertEqual(diff_signals.reserved_paths(rs, [path]), [f"{path} ({AREA})"], path)
                    self.assertEqual(diff_signals.reserved_paths(rs, [f"{folder}/intents/INTENT-1.md"]), [])
        rs = risk.rule_set(cfg("risks:\n  areas:\n    product_scope:\n      paths: [mine/**]\n      route: normal\n"))
        hits = diff_signals.reserved_paths(rs, ["product/prd.md", "mine/x.md", "src/app.py"])
        self.assertEqual(hits, [f"product/prd.md ({AREA})", f"mine/x.md ({AREA})"])


class TheAdviceTests(unittest.TestCase):
    def test_a_path_in_the_area_names_the_gate_its_change_needs(self):
        """`aidd risk --paths` on a product scope file says a person approves a change there, by the action's name; a path in no
        such area says nothing of it."""
        for path, named in (("product/prd.md", True), ("product/intents/order.md", True), ("product/intents/INTENT-1.md", False), ("src/app.py", False)):
            with self.subTest(path=path):
                answer = risk.advice(cfg(), [path])
                self.assertEqual("`product_scope.approve`" in answer["next"]["what"], named, answer["next"]["what"])
        self.assertEqual(resources.load_json("risks.json")["areas"][AREA]["action"], "product_scope.approve")


class NoOtherAnswerMovesTests(unittest.TestCase):
    """The area and the action lower no level and raise no route for a path outside them: the same answers, with the area
    left out of the rule set, over every eighth tracked file of this repository and the area's own paths."""

    def without_the_area(self, rs: risk.RuleSet) -> risk.RuleSet:
        return risk.RuleSet({k: v for k, v in rs.areas.items() if k != AREA}, rs.actions, rs.rules, rs.ignored, rs.environments)

    def corpus(self) -> list[str]:
        tracked = git(ROOT, "ls-files").splitlines()[::8] if (ROOT / ".git").exists() else []  # every eighth: the corpus stays inside the test's time
        own = [f"product/{n}" for n in FILES] + [f"a/product/{n}" for n in FILES] + ["product/intents/INTENT-1.md", "product/notes.md"]
        return [*tracked, *own]

    def test_every_route_and_edit_level_is_the_same_without_the_area(self):
        for label, config_ in (
            ("no config", None),
            ("solo", cfg()),
            (
                "a delegation",
                cfg(
                    "delegation:\n  by: Maya Lee <maya@users.noreply.github.com>\n  at: \"2026-11-01T09:00:00Z\"\n  decides: [spec.approve]\n  default_branch: main\n  review_due: '2099-01-01'\n"
                ),
            ),
        ):
            rs = risk.rule_set(config_)
            bare = self.without_the_area(rs)
            moved = []
            for path in self.corpus():
                with_area, without = risk.route_for(rs, [path]), risk.route_for(bare, [path])
                levels = (risk.edit_level(rs, [path])[0], risk.edit_level(bare, [path])[0])
                if (with_area.route, with_area.dimensions) != (without.route, without.dimensions) or levels[0] != levels[1]:
                    moved.append((path, with_area.route, without.route, levels))
            with self.subTest(label):
                self.assertEqual(moved, [])


if __name__ == "__main__":
    unittest.main()
