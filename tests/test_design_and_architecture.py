"""One design system and one architecture overview per repository.

The repository keeps one `DESIGN.md` and one `design/tokens.json` (Design Tokens Format Module 2025.10), which every
prototype and per-Spec design spec uses and never copies, and one living architecture overview in
`docs/architecture/README.md` (arc42-lite, with a C4 container diagram and fitness functions as ordinary tests).
"""

import json
import re
import tomllib
import unittest
from pathlib import Path

from helpers import ROOT, adopted_repo, git, replayed_corpus, run_cli

from aidd import config, repo, resources, rules

ASSETS = ROOT / ".agents" / "skills" / "aidd" / "assets"
TEAM = ROOT / "plugins" / "aidd-team"
PROTOTYPING = TEAM / "skills" / "prototyping"
BARE_TEAM = 'aidd_version = "1.0.0"\nprofile = "team"\n[owners]\napprovers = ["@a", "@b"]\n'

# The token types the Design Tokens Format Module 2025.10 defines.
DTCG_TYPES = {
    "color",
    "dimension",
    "fontFamily",
    "fontWeight",
    "duration",
    "cubicBezier",
    "number",
    "strokeStyle",
    "border",
    "transition",
    "shadow",
    "gradient",
    "typography",
}
ALIAS = re.compile(r"^\{([^{}]+)\}$")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def tokens(tree: dict, path: tuple[str, ...] = (), inherited: str | None = None):
    """Every token in a DTCG tree as (dotted name, token, its resolved $type)."""
    kind = tree.get("$type", inherited)
    if "$value" in tree:
        yield ".".join(path), tree, kind
        return
    for key, child in tree.items():
        if not key.startswith("$"):
            yield from tokens(child, (*path, key), kind)


def resolve(tree: dict, value):
    """An alias's target token, else the value itself."""
    while isinstance(value, str) and (m := ALIAS.match(value)):
        node = tree
        for part in m.group(1).split("."):
            node = node[part]
        value = node["$value"]
    return value


def dtcg_errors(tree: dict) -> list[str]:
    """What breaks the Design Tokens format's structure: a token without a type, an unknown type, a group name or token
    name with a character the format reserves, an alias that resolves nowhere, and a value of the wrong shape."""
    errs = []
    for name, token, kind in tokens(tree):
        for part in name.split("."):
            if part.startswith("$") or any(c in part for c in "{}."):
                errs.append(f"{name}: a name may not start with $ or hold {{, }}, or .")
        if kind not in DTCG_TYPES:
            errs.append(f"{name}: $type {kind!r} is not a Design Tokens type (on the token or a parent group)")
            continue
        try:
            value = resolve(tree, token["$value"])
        except (KeyError, TypeError):
            errs.append(f"{name}: alias {token['$value']!r} resolves to no token")
            continue
        if kind == "color" and not (isinstance(value, dict) and value.get("colorSpace") and len(value.get("components", [])) == 3):
            errs.append(f"{name}: a color is an object with colorSpace and three components")
        if kind in ("dimension", "duration") and not (isinstance(value, dict) and isinstance(value.get("value"), (int, float)) and value.get("unit")):
            errs.append(f"{name}: a {kind} is an object with a number value and a unit")
        if kind == "dimension" and isinstance(value, dict) and value.get("unit") not in ("px", "rem"):
            errs.append(f"{name}: a dimension's unit is px or rem")
        if kind == "duration" and isinstance(value, dict) and value.get("unit") not in ("ms", "s"):
            errs.append(f"{name}: a duration's unit is ms or s")
        if kind == "fontFamily" and not isinstance(value, (str, list)):
            errs.append(f"{name}: a fontFamily is a string or a list of strings")
        if kind == "fontWeight" and not (isinstance(value, (int, float)) and 1 <= value <= 1000):
            errs.append(f"{name}: a numeric fontWeight is 1 to 1000")
        if kind == "typography":
            if not isinstance(value, dict) or set(value) != {"fontFamily", "fontSize", "fontWeight", "letterSpacing", "lineHeight"}:
                errs.append(f"{name}: a typography token has fontFamily, fontSize, fontWeight, letterSpacing, and lineHeight")
            else:
                for part, sub in value.items():
                    try:
                        resolve(tree, sub)
                    except (KeyError, TypeError):
                        errs.append(f"{name}.{part}: alias {sub!r} resolves to no token")
    return errs


class TemplateTests(unittest.TestCase):
    def test_the_design_md_template_has_every_section(self):
        text = read(ASSETS / "DESIGN.md")
        for heading in (
            "## Overview",
            "## Colors",
            "## Themes",
            "## Typography",
            "## Layout",
            "## Elevation & Depth",
            "## Shapes",
            "## Motion",
            "## Components",
            "## Patterns",
            "## Accessibility",
            "## Platforms",
            "## Changing the design system",
        ):
            self.assertIn(heading, text, heading)
        for word in (
            "prefers-reduced-motion",
            "WCAG 2.2 AA",
            "design/tokens.json",
            "### Web",
            "### iOS",
            "### Android",
            "empty",
            "error",
            "Forms",
            "Navigation",
        ):
            self.assertIn(word, text, word)
        self.assertIn("{{today}}", text)

    def test_the_tokens_template_is_valid_dtcg(self):
        tree = json.loads(read(ASSETS / "tokens.json"))
        self.assertEqual(dtcg_errors(tree), [])
        kinds = {kind for _, _, kind in tokens(tree)}
        self.assertTrue({"color", "dimension", "fontFamily", "fontWeight", "duration", "typography"} <= kinds, kinds)
        # Roles alias raw values, so a prototype uses a role and a person changes a hue in one place.
        self.assertTrue(any(isinstance(t["$value"], str) and ALIAS.match(t["$value"]) for _, t, k in tokens(tree) if k == "color"))

    def test_the_check_catches_a_broken_tokens_file(self):
        self.assertTrue(dtcg_errors({"color": {"accent": {"$value": {"colorSpace": "srgb", "components": [0, 0, 1]}}}}))  # no $type
        self.assertTrue(dtcg_errors({"color": {"$type": "color", "accent": {"$value": "{color.missing}"}}}))
        self.assertTrue(dtcg_errors({"space": {"$type": "dimension", "2": {"$value": "8px"}}}))  # a string, not an object
        self.assertTrue(dtcg_errors({"x": {"$type": "colour", "a": {"$value": 1}}}))

    def test_the_architecture_template_is_arc42_lite_and_living(self):
        text = read(ASSETS / "architecture.md")
        for heading in (
            "## Context and scope",
            "## Building blocks",
            "## Runtime view",
            "## Deployment view",
            "## Cross-cutting concepts",
            "## Quality targets",
            "## Risks and technical debt",
            "## Glossary",
            "## Fitness functions",
        ):
            self.assertIn(heading, text, heading)
        self.assertIn("C4Container", text)
        self.assertIn("sequenceDiagram", text)
        self.assertIn("docs/adr/", text)
        self.assertIn("living", text.lower())
        for tool in ("import-linter", "dependency-cruiser", "ArchUnit", "NetArchTest", "[[tests]]"):
            self.assertIn(tool, text, tool)
        self.assertNotRegex(text, r"(?:import-linter|dependency-cruiser|ArchUnit|NetArchTest)[ @=]+v?\d", "no pinned versions")

    def test_the_tech_spec_starts_from_the_overview(self):
        text = read(ASSETS / "tech-spec.md")
        self.assertIn("docs/architecture/README.md", text)
        self.assertIn("only what changes", text)


class NewCommandTests(unittest.TestCase):
    def test_new_design_system_writes_the_two_files_once(self):
        with adopted_repo() as root:
            code, out = run_cli("new", "design-system")
            self.assertEqual(code, 0, out)
            self.assertIn("DESIGN.md", out)
            self.assertIn("design/tokens.json", out)
            self.assertTrue((root / "DESIGN.md").is_file())
            self.assertNotIn("{{", read(root / "DESIGN.md"))
            self.assertEqual(dtcg_errors(json.loads(read(root / "design" / "tokens.json"))), [])
            code, out = run_cli("new", "design-system")
            self.assertEqual(code, 2, out)
            self.assertIn("exists", out)

    def test_new_architecture_writes_the_overview(self):
        with adopted_repo() as root:
            code, out = run_cli("new", "architecture")
            self.assertEqual(code, 0, out)
            overview = root / "docs" / "architecture" / "README.md"
            self.assertTrue(overview.is_file())
            self.assertNotIn("{{", read(overview))
            self.assertIn("C4Container", read(overview))

    def test_a_repository_document_takes_no_id(self):
        with adopted_repo():
            code, out = run_cli("new", "spec")
            self.assertEqual(code, 2, out)
            self.assertIn("id", out)

    def test_the_repository_documents_are_their_own_kind(self):
        self.assertEqual(set(repo.REPO_DOCS), {"design-system", "architecture", "data-map", "vendors", "glossary"})
        self.assertFalse(set(repo.REPO_DOCS) & set(repo.DOC_TEMPLATES))


class RoutingTests(unittest.TestCase):
    def assess(self, path: str) -> rules.Assessment:
        return rules.assess_paths(config.load_text(BARE_TEAM), [path])

    def test_the_design_system_is_reviewed_but_not_major(self):
        for path in ("DESIGN.md", "design/tokens.json", "apps/web/DESIGN.md", "packages/ui/design/tokens.json", "brand.tokens.json"):
            a = self.assess(path)
            self.assertEqual(a.required_route, "normal", path)
            self.assertTrue(any("baseline:design-system" in r for r in a.reasons), (path, a.reasons))
        for path in ("docs/design/SPEC-1/checkout-flow.md", "docs/architecture/README.md", "src/components/Button.tsx"):
            self.assertEqual(self.assess(path).required_route, "minor", path)

    def test_a_pass_and_a_fail_case_pin_the_rule(self):
        by = {name: d for name, d, _ in replayed_corpus()}
        failing = by["01-minor-docs/design-system-in-a-minor-change"]
        self.assertEqual(failing.codes(), ["fail route.too_low"])
        self.assertIn("baseline:design-system", next(f.message for f in failing.findings if f.code == "route.too_low"))
        self.assertEqual(by["02-normal-feature/design-system-inside-a-normal-spec"].decision, "pass")

    def test_a_routing_scenario_names_it(self):
        scenarios = tomllib.loads(read(ROOT / "evals" / "routing" / "scenarios.toml"))["scenario"]
        found = [s for s in scenarios if "DESIGN.md" in s.get("paths", [])]
        self.assertEqual([s["expected"]["route"] for s in found], ["normal"])

    def test_the_generated_tables_list_the_rule(self):
        self.assertIn("`baseline:design-system`", read(ROOT / ".agents" / "skills" / "aidd" / "references" / "routes.md"))
        self.assertIn("`baseline:design-system`", read(ROOT / "docs" / "METHOD.md"))
        self.assertIn("baseline:design-system", {r["name"] for r in resources.baseline()["risk_rules"]})


class DriftWarningTests(unittest.TestCase):
    SPEC = """+++
aidd_version = "1.0.0"
kind = "spec"
id = "SPEC-7"
title = "Split the bill"
owner_team = "shop"
type = "feat"
route = "normal"
confidence = "high"
open_questions = []
trace_id = "spec-7"
assisted_by = []
rollback = "Revert the change."

[risk]
summary = "Checkout gains a split step."
dimensions = []
reversible = true

[[tasks]]
id = "SPEC-7-T1"
title = "Split"
scope = ["src/web/split/"]

[design]
files = ["docs/design/SPEC-7/**"]

[tests]
files = ["tests/test_split.py"]

[[tests.commands]]
name = "split"
command = ["python3", "tests/test_split.py"]
new_behavior = true
covers = ["A1"]
+++

## Intent

Split the bill.

## Acceptance

- A1: a customer splits the total in two.

## Design

A split step after the cart.

## Policy conflicts

none

## Rollback

Revert.
"""

    def warnings(self, root: Path, own_tokens: bool, repo_tokens: bool) -> list[str]:
        spec = root / "specs" / "SPEC-7.md"
        spec.parent.mkdir(parents=True, exist_ok=True)
        spec.write_text(self.SPEC, encoding="utf-8")
        folder = root / "docs" / "design" / "SPEC-7"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "flow.md").write_text("SPEC-7 flow\n", encoding="utf-8")
        if own_tokens:
            (folder / "split.tokens.json").write_text("{}\n", encoding="utf-8")
        if repo_tokens:
            (root / "design").mkdir(exist_ok=True)
            (root / "design" / "tokens.json").write_text(read(ASSETS / "tokens.json"), encoding="utf-8")
        git(root, "add", "-A")
        return [e for e in repo.validate_file(spec) if "tokens" in e]

    def test_own_tokens_beside_the_repository_s_warn(self):
        with adopted_repo() as root:
            found = self.warnings(root, own_tokens=True, repo_tokens=True)
            self.assertEqual(len(found), 1, found)
            self.assertTrue(found[0].startswith("warning: "), found)
            self.assertIn("docs/design/SPEC-7/split.tokens.json", found[0])
            self.assertIn("design/tokens.json", found[0])

    def test_no_warning_without_a_repository_design_system_or_without_a_copy(self):
        with adopted_repo() as root:
            self.assertEqual(self.warnings(root, own_tokens=True, repo_tokens=False), [])
        with adopted_repo() as root:
            self.assertEqual(self.warnings(root, own_tokens=False, repo_tokens=True), [])


class TeamTests(unittest.TestCase):
    def role(self, key: str) -> dict:
        return resources.roles()["roles"][key]

    def test_each_role_names_the_repository_design_system_in_one_line(self):
        for key in ("product-designer", "developer", "tester", "reviewer"):
            self.assertIn("`DESIGN.md`", self.role(key)["does"], key)
            self.assertIn("`DESIGN.md`", read(TEAM / "agents" / f"{key}.md"), key)

    def test_mvp_day_0_runs_the_designer_beside_the_architect(self):
        flow = next(f for f in resources.roles()["loop"]["flows"] if f["command"] == "mvp")
        self.assertIn(["architect", "product-designer"], flow["runs"])
        text = read(TEAM / "commands" / "mvp.md")
        day0 = text.split("**Day 0.**", 1)[1].split("\n3. ", 1)[0]
        for word in ("`aidd-team:product-designer`", "`DESIGN.md`", "`design/tokens.json`", "`docs/architecture/README.md`", "picked"):
            self.assertIn(word, day0, word)

    def test_onboarding_drafts_both_read_only(self):
        flow = next(f for f in resources.roles()["loop"]["flows"] if f["command"] == "onboard")
        self.assertIn("product-designer", flow["runs"][0])
        text = read(TEAM / "commands" / "onboard.md")
        for word in ("`aidd-team:product-designer`", "`DESIGN.md`", "draft", "accept"):
            self.assertIn(word, text, word)

    def test_prototypes_use_the_repository_design_system_and_never_copy_it(self):
        skill, contract = read(PROTOTYPING / "SKILL.md"), read(PROTOTYPING / "references" / "design-system-contract.md")
        for text in (skill, contract):
            self.assertIn("`DESIGN.md`", text)
            self.assertIn("`design/tokens.json`", text)
            self.assertIn("never cop", text)
            self.assertIn("separate change", text)
        self.assertNotIn("tokens.tokens.json", contract)

    def test_a_raw_value_lint_is_an_ordinary_test_command(self):
        pack = next(d for d in resources.roles()["domains"] if d["slug"] == "web-front-end")
        lint = [t for t in pack["tests"] if "declaration-strict-value" in t["how"]]
        self.assertEqual(len(lint), 1)
        self.assertIn("color-no-hex", lint[0]["how"])
        self.assertIn("ESLint", lint[0]["how"])
        self.assertIn("declaration-strict-value", read(TEAM / "skills" / "web-front-end" / "SKILL.md"))

    def test_the_architect_writes_fitness_functions(self):
        text = read(TEAM / "agents" / "architect.md")
        self.assertIn("fitness function", text)
        self.assertIn("After Ship", text)
        self.assertIn("fast-lane docs change", text)
        practice = read(TEAM / "skills" / "decision-record" / "SKILL.md")
        for tool in ("import-linter", "dependency-cruiser", "ArchUnit", "NetArchTest"):
            self.assertIn(tool, practice, tool)


class DocsTests(unittest.TestCase):
    def test_the_how_to_recipe_and_the_glossary(self):
        how = read(ROOT / "docs" / "HOW-TO.md")
        self.assertIn("**…keep one design system and one architecture overview?**", how)
        self.assertIn("aidd new design-system", how)
        self.assertIn("aidd new architecture", how)
        glossary = read(ROOT / "docs" / "GLOSSARY.md")
        for term in ("| Design system |", "| Architecture overview |", "| Fitness function |"):
            self.assertIn(term, glossary, term)
        self.assertIn("DESIGN.md", read(ROOT / "docs" / "TEAM.md"))

    def test_the_cli_reference_lists_the_kinds(self):
        cli_md = read(ROOT / "docs" / "CLI.md")
        self.assertIn("design-system", cli_md)
        self.assertIn("architecture", cli_md)


class EngineeringDepthTests(unittest.TestCase):
    """Depth in the documents and skills a team already has, never a new kind, role, pack, or check: the tech spec's
    non-functional needs and data model, contract and visual-regression recipes in the packs, and codemods."""

    def test_the_tech_spec_has_nfrs_and_a_data_model(self):
        text = (ASSETS / "tech-spec.md").read_text(encoding="utf-8")
        nfr = text.split("### Non-functional requirements", 1)[1].split("\n## ", 1)[0].split("\n### ", 1)[0]
        for need in ("Availability", "Latency", "Throughput", "Scale and cost", "Capacity headroom", "Data volume"):
            self.assertIn(need, nfr, need)
        data = text.split("### Data model", 1)[1].split("\n## ", 1)[0].split("\n### ", 1)[0]
        for word in ("erDiagram", "keys", "retention", "data map"):
            self.assertIn(word, data, word)
        self.assertNotIn("tech-spec-nfr", repo.DOC_TEMPLATES)

    def test_the_packs_carry_contract_and_visual_regression_recipes(self):
        domains = {d["slug"]: {t["name"]: t["how"] for t in d["tests"]} for d in resources.roles()["domains"]}
        api = domains["apis-and-services"]
        self.assertIn("can-i-deploy", api["Contract tests"])
        self.assertIn("oasdiff breaking --fail-on ERR", api["Breaking-change diff"])
        # The screenshot matrix is the prototyping skill's; the web pack points to it.
        proto = (TEAM / "skills" / "prototyping" / "SKILL.md").read_text(encoding="utf-8")
        row = next(r for r in proto.splitlines() if r.startswith("| Screenshot matrix |"))
        self.assertIn("toHaveScreenshot", row)
        self.assertIn("tests.files", row)
        web = next(d for d in resources.roles()["domains"] if d["slug"] == "web-front-end")
        self.assertIn({"owner": "prototyping", "tests": ["Screenshot matrix"]}, web["tests_elsewhere"])

    def test_codemods_live_in_the_dependency_upgrade_skill(self):
        # The skill states the rule and links its reference, which holds the tools and the steps (the skill's size cap).
        folder = TEAM / "skills" / "dependency-upgrade"
        text = (folder / "SKILL.md").read_text(encoding="utf-8")
        section = text.split("### Codemods", 1)[1].split("\n## ", 1)[0].split("\n### ", 1)[0]
        self.assertIn("references/codemods.md", section)
        guide = (folder / "references" / "codemods.md").read_text(encoding="utf-8")
        for word in ("ast-grep", "OpenRewrite", "jscodeshift", "Dry run", "diff", "tests"):
            self.assertIn(word, guide, word)
        self.assertIn("codemod", (TEAM / "agents" / "architect.md").read_text(encoding="utf-8").split("## Playbook", 1)[1])


if __name__ == "__main__":
    unittest.main()
