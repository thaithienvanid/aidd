"""The modular monolith in a monorepo: aidd's default shape for a new project.

A practice skill holds the judgement (`aidd-team:modular-monolith`, listed by the architect and the developer, preloaded
by no role). Two open choices leave the tools to the team (`modular-monolith:module-boundaries`, `ci-pipeline:workspace`).
A product default (`modular_monolith` in `project.defaults`) is on for a new project; `aidd init` writes it off, with
the reason, in a repository that already has code. A change to the violations baseline is in the built-in
`module_boundaries` area (major), and the skill tells a team to add a config area for its modules' contracts. The assets give the module README and the architecture overview's module map.
"""

import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, git, run_cli

from aidd import config
from aidd.docsgen import pack_budget
from aidd.docsgen import token_caps
from aidd.docsgen import pack_render
from aidd.setup import detection
from aidd.setup import config_template
from aidd.knowledge import library_checks, role_text, standards, team_registry
from aidd.config import project
from aidd.kernel import resources

TEAM = ROOT / "plugins" / "aidd-team"
SKILL_DIR = TEAM / "skills" / "modular-monolith"
ASSETS = ROOT / ".agents" / "skills" / "aidd" / "assets"
NAME = "modular-monolith"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class SkillTests(unittest.TestCase):
    def test_the_skill_is_registered_and_listed_but_never_preloaded(self):
        data = team_registry.roles()
        self.assertIn(NAME, data["practices"])
        for key in ("architect", "developer"):
            self.assertIn(NAME, data["roles"][key]["practices"], key)
        for key, r in data["roles"].items():
            self.assertNotIn(NAME, r.get("preload", []), key)
        self.assertIn(NAME, role_text.practice_names())

    def test_the_standards_name_the_public_sources_with_a_date(self):
        data = team_registry.roles()
        ids = [s if isinstance(s, str) else s["id"] for s in data["practices"][NAME]["standards"]]
        for sid in ("cloudevents", "shopify-deconstructing-the-monolith", "spring-modulith-application-events", "transactional-outbox", "dora-metrics"):
            self.assertIn(sid, ids)
            entry = data["standards"][sid]
            self.assertTrue(entry.get("checked"), sid)
        self.assertEqual(data["standards"]["cloudevents"]["edition"], "1.0.2")

    def test_the_skill_keeps_the_template_and_its_caps(self):
        text = read(SKILL_DIR / "SKILL.md")
        self.assertLessEqual(len(pack_budget.description(text)), pack_budget.DESCRIPTION_CHARS)
        self.assertLessEqual(token_caps.estimate_tokens(text), token_caps.PRACTICE_TOKENS)
        refs = sorted(p.name for p in (SKILL_DIR / "references").glob("*.md"))
        self.assertEqual(refs, ["boundaries.md", "events-and-data.md", "migrate-and-extract.md"])
        for ref in refs:
            self.assertLessEqual(token_caps.estimate_tokens(read(SKILL_DIR / "references" / ref)), token_caps.REFERENCE_TOKENS, ref)
        self.assertEqual([p for p in pack_budget.problems() if p["where"] == f"practice {NAME}"], [])
        # Its open choice stays in the SKILL.md, so the skill keeps three references.
        self.assertEqual(pack_render.open_choices_placement(NAME), "skill")

    def test_the_skill_says_when_not_and_holds_the_rules(self):
        text = read(SKILL_DIR / "SKILL.md")
        head = text.split("\n## ", 1)[0]
        for word in ("client", "existing structure", "ADR", "modular_monolith"):
            self.assertIn(word, head, word)
        for word in ("apps/", "modules/", "packages/", "docs/", "api/", "internal/", "shared kernel", "outbox", "saga", "`module_boundaries`"):
            self.assertIn(word, text, word)
        for reason in ("independent scaling", "runtime", "fault isolation", "deploy contention", "compliance"):
            self.assertIn(reason, text, reason)
        self.assertNotRegex(text, r"\]\((?:\.\./){2,}", "the skill links nothing outside its plugin")

    def test_the_references_hold_events_boundaries_and_migration(self):
        events = read(SKILL_DIR / "references" / "events-and-data.md")
        for word in (
            "specversion",
            "<module>.<aggregate>.<past-verb>.v<N>",
            "outbox",
            "inbox",
            "at least once",
            "idempotent",
            ".v2",
            "saga",
            "purge",
            "tenantid",
        ):
            self.assertIn(word, events, word)
        bounds = read(SKILL_DIR / "references" / "boundaries.md")
        for word in (
            "pg_constraint",
            "table prefix",
            "D1",
            "project.waivers",
            "until",
            "fixture",
            "modular-monolith:module-boundaries",
            "ci-pipeline:workspace",
        ):
            self.assertIn(word, bounds, word)
        moves = read(SKILL_DIR / "references" / "migrate-and-extract.md")
        for word in ("Phase", "Exit criteria", "baseline", "ADR", "remote client"):
            self.assertIn(word, moves, word)


class OpenChoiceTests(unittest.TestCase):
    def test_the_two_choices_are_declared_once_with_a_default_in_words(self):
        choices = standards.open_choices()
        for ref, word in (("modular-monolith:module-boundaries", "baseline"), ("ci-pipeline:workspace", "lockfile")):
            self.assertIn(ref, choices)
            self.assertIn(word, choices[ref]["default"], ref)
        self.assertEqual(standards.choice_problems(), [])
        self.assertEqual(standards.deciding_problems(), [])
        self.assertEqual(library_checks.method_problems(choices), [])


class ProductDefaultTests(unittest.TestCase):
    def test_the_default_is_on_unless_off_names_it(self):
        self.assertIn("modular_monolith", project.PROJECT_DEFAULTS)
        off = resources.load_json("config.schema.json")["properties"]["project"]["properties"]["defaults"]["properties"]["disabled"]
        self.assertIn("modular_monolith", off["properties"])
        self.assertTrue(project.project_defaults(None)["modular_monolith"])
        cfg = config.load_text('aidd_version: "1.0.0"\nprofile: solo\nproject:\n  defaults:\n    disabled: {modular_monolith: "a client project: ADR 0002"}\n')
        self.assertFalse(project.project_defaults(cfg)["modular_monolith"])

    def test_detect_tells_an_empty_repository_from_existing_code(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.assertFalse(detection.detect(root)["existing_code"], "an empty repository starts in the shape")
            (root / "README.md").write_text("# x\n", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("print(1)\n", encoding="utf-8")
            self.assertFalse(detection.detect(root)["existing_code"], "a near-empty repository starts in the shape")
            for i in range(detection.EXISTING_CODE_FILES):
                (root / "src" / f"m{i}.py").write_text("x = 1\n", encoding="utf-8")
            self.assertTrue(detection.detect(root)["existing_code"])

    def test_the_block_writes_it_off_only_for_existing_code(self):
        on = config_template.config_text(config_template.ConfigTemplate("solo", approvers=["@me"]))
        self.assertNotIn("modular_monolith", on)
        self.assertTrue(project.project_defaults(config.load_text(on))["modular_monolith"])
        off = config_template.config_text(config_template.ConfigTemplate("solo", approvers=["@me"], existing_code=True))
        cfg = config.load_text(off)
        self.assertEqual(cfg.get("project", "defaults", "disabled"), {"modular_monolith": project.EXISTING_STRUCTURE})
        self.assertIn("ADR", project.EXISTING_STRUCTURE)
        both = config.load_text(config_template.config_text(config_template.ConfigTemplate("solo", approvers=["@me"], ui=False, existing_code=True)))
        self.assertEqual(len(both.get("project", "defaults", "disabled")), 5)

    def test_aidd_init_keeps_an_existing_repository_as_it_is(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q", "-b", "main")
            (root / "src").mkdir()
            for i in range(detection.EXISTING_CODE_FILES):
                (root / "src" / f"m{i}.py").write_text("x = 1\n", encoding="utf-8")
            code, out = run_cli(
                "init", str(root), "--profile", "solo", "--approvers", "email:me@example.com", "--ci", "none", "--harness", "none", "--no-skill"
            )
            self.assertEqual(code, 0, out)
            self.assertIn("modular_monolith", out)
            cfg = config.load_file(".aidd/config.yaml", str(root))
            self.assertFalse(project.project_defaults(cfg)["modular_monolith"])
            code, out = run_cli("validate", str(root / ".aidd" / "config.yaml"))
            self.assertEqual(code, 0, out)

    def test_the_owner_skill_and_the_mvp_name_it(self):
        self.assertIn("`modular_monolith`", read(TEAM / "skills" / "product-defaults" / "SKILL.md"))
        day0 = read(TEAM / "commands" / "mvp.md").split("2. **Day 0.**", 1)[1].split("\n3. ", 1)[0]
        self.assertIn("modular monolith", day0)
        self.assertIn("modular-monolith practice skill", day0)


class RiskRuleTests(unittest.TestCase):
    def test_the_naming_skill_and_this_skill_spell_the_event_type_alike(self):
        pattern = "<module>.<aggregate>.<past-verb>.v<N>"
        systems = read(TEAM / "skills" / "naming" / "references" / "systems.md")
        self.assertIn(pattern, systems)
        self.assertIn(pattern, read(SKILL_DIR / "references" / "events-and-data.md"))
        self.assertIn(pattern, read(ASSETS / "module-readme.md"))


class AssetTests(unittest.TestCase):
    def test_the_module_readme_has_every_section(self):
        text = read(ASSETS / "module-readme.md")
        for word in (
            "Purpose",
            "Owner",
            "Subdomain",
            "## Public API",
            "## Owned data",
            "Personal data",
            "## Events",
            "Publishes",
            "Consumes",
            "## Dependencies",
            "## Decisions",
        ):
            self.assertIn(word, text, word)
        self.assertIn("assets/module-readme.md", read(SKILL_DIR / "SKILL.md"))

    def test_the_architecture_overview_has_the_module_map_and_its_fitness_functions(self):
        text = read(ASSETS / "architecture.md")
        self.assertIn("## Module map", text)
        self.assertIn("| Module | Purpose | Owner | Subdomain | Owned data | Publishes | Consumes |", text)
        fitness = text.split("## Fitness functions", 1)[1].split("\n## ", 1)[0]
        for word in ("module-boundaries", "aidd-team:modular-monolith"):
            self.assertIn(word, fitness, word)
        # The data check and the dependency rules the overview used to carry live in the pack's boundaries reference.
        boundaries = read(SKILL_DIR / "references" / "boundaries.md")
        for word in ("pg_constraint", "table prefix", "No cycle between modules", "baseline never grows"):
            self.assertIn(word, boundaries, word)


if __name__ == "__main__":
    unittest.main()
