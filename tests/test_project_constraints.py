"""The project's constraints and rules: `[project]` in .aidd/config.yaml, a technology radar, hosting, a budget, the
team's own rules with their why, and waivers a person approves. `aidd validate` checks them, `aidd gate --paths`
and `aidd owners` print the ones that apply, and `aidd init` pre-fills the radar from what it detects."""

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from helpers import adopted_repo, git, run_cli

from aidd import config
from aidd.workitems import validation
from aidd.setup import config_template
from aidd.knowledge import owners
from aidd.config import project

HEAD = 'aidd_version: "1.0.0"\nprofile: team\nowners: {approvers: ["@org/leads"]}\n'
TODAY = dt.date(2026, 9, 30)

FULL = """
project:
  hosting: one VPS in the EU

  stack:
    adopt: [Python, PostgreSQL]
    trial: [htmx]
    hold: [MongoDB]

  budget:
    max_infra_per_month: 50
    currency: EUR
    new_paid_service: ask

  rules:
    - id: no-orm-raw-sql
      level: should
      statement: "Query through the repository layer, not raw SQL in handlers."
      why: One place to review every query.
      applies: ["src/api/**"]
      check: lint
      source: docs/adr/0003-repository-layer.md
      owner: "@org/leads"
      review_due: "2027-03-01"

    - id: money-in-minor-units
      level: must
      statement: Store money as an integer count of the currency's minor unit.
      why: Floats lose minor units on rounding.
      owner: "@alice"

    - id: docs-voice
      level: may
      statement: Write docs in the second person.
      why: It reads as instructions.
      owner: "@bob"

  waivers:
    - rule: no-orm-raw-sql
      reason: The reporting query needs a window function the layer lacks.
      approved_by: "@alice"
      until: "2099-12-31"
"""


def load(extra: str = FULL) -> config.Config:
    return config.load_text(HEAD + extra)


def invalid(extra: str) -> bool:
    try:
        load(extra)
    except config.ConfigError:
        return True
    return False


RULE_ITEM = '    - id: r1\n      level: must\n      statement: s\n      why: w\n      owner: "@a"\n'
RULE = "project:\n  rules:\n" + RULE_ITEM


def waiver_item(who: str = '"@a"', until: str = '"2027-01-01"', rule: str = "r1") -> str:
    return f"    - rule: {rule}\n      reason: r\n      approved_by: {who}\n      until: {until}\n"


def with_waivers(*items: str, rules: str = RULE) -> str:
    """`rules` (a `project:` block) with a `waivers` list of `items` under the same `project` key."""
    return rules + "  waivers:\n" + "".join(items)


class SchemaTests(unittest.TestCase):
    def test_every_field_is_accepted(self):
        cfg = load()
        p = cfg.get("project")
        self.assertEqual(p["stack"]["hold"], ["MongoDB"])
        self.assertEqual(p["budget"], {"max_infra_per_month": 50, "currency": "EUR", "new_paid_service": "ask"})
        self.assertEqual(p["hosting"], "one VPS in the EU")
        self.assertEqual([r["id"] for r in p["rules"]], ["no-orm-raw-sql", "money-in-minor-units", "docs-voice"])
        self.assertEqual(p["rules"][0]["review_due"], "2027-03-01")
        self.assertEqual(p["waivers"][0]["until"], "2099-12-31")

    def test_each_field_is_checked(self):
        bad = {
            "unknown level": RULE.replace("level: must", "level: shall"),
            "no why": RULE.replace("      why: w\n", ""),
            "no owner": RULE.replace('      owner: "@a"\n', ""),
            "no statement": RULE.replace("      statement: s\n", ""),
            "id with spaces": RULE.replace("id: r1", 'id: "r 1"'),
            "absolute applies": RULE + '      applies: ["/etc/**"]\n',
            "empty check": RULE + '      check: ""\n',
            "bad review_due": RULE + "      review_due: soon\n",
            "source with wildcard": RULE + '      source: "docs/adr/*.md"\n',
            "unknown rule key": RULE + "      severity: high\n",
            "unknown paid switch": "project:\n  budget:\n    new_paid_service: sometimes\n",
            "negative budget": "project:\n  budget:\n    max_infra_per_month: -1\n    currency: EUR\n",
            "budget without currency": "project:\n  budget:\n    max_infra_per_month: 10\n",
            "lower-case currency": "project:\n  budget:\n    max_infra_per_month: 10\n    currency: eur\n",
            "empty stack item": 'project:\n  stack:\n    adopt: [""]\n',
            "repeated stack item": "project:\n  stack:\n    adopt: [Go, Go]\n",
            "unknown ring": "project:\n  stack:\n    assess: [Rust]\n",
            "empty hosting": 'project:\n  hosting: ""\n',
            "unknown project key": "project:\n  team_size: 3\n",
            "waiver without until": 'project:\n  waivers:\n    - rule: r1\n      reason: r\n      approved_by: "@a"\n',
            "waiver without reason": 'project:\n  waivers:\n    - rule: r1\n      approved_by: "@a"\n      until: "2026-10-01"\n',
            "waiver with a bad date": 'project:\n  waivers:\n    - rule: r1\n      reason: r\n      approved_by: "@a"\n      until: next week\n',
        }
        for name, extra in bad.items():
            with self.subTest(name):
                self.assertTrue(invalid(extra), name)
        self.assertFalse(invalid(RULE))
        self.assertFalse(invalid("project:\n  budget:\n    new_paid_service: forbidden\n"))


class FindingTests(unittest.TestCase):
    def findings(self, extra: str, today: dt.date = TODAY):
        return project.project_findings(load(extra), today)

    def test_a_valid_project_has_no_findings(self):
        self.assertEqual(self.findings(FULL), ([], []))

    def test_duplicate_rule_ids_are_an_error(self):
        errors, _ = self.findings(RULE + RULE_ITEM.replace("level: must", "level: should"))
        self.assertTrue(any("r1" in e and "unique" in e for e in errors), errors)

    def test_a_waiver_of_an_unknown_rule_is_an_error(self):
        errors, _ = self.findings(with_waivers(waiver_item(rule="r2")))
        self.assertTrue(any("'r2'" in e and "no rule" in e for e in errors), errors)

    def test_a_waiver_approved_by_an_agent_or_a_bot_is_an_error(self):
        for who in ("agent:developer", "claude[bot]", "@codex-agent", "acme:agent:developer"):
            extra = 'identities:\n  bots: ["codex-agent"]\n' + with_waivers(waiver_item(who=f'"{who}"'))
            with self.subTest(who):
                errors, _ = self.findings(extra)
                self.assertTrue(any("a person approves a waiver" in e for e in errors), errors)

    def test_a_waiver_warns_two_weeks_before_it_expires_and_fails_once_expired(self):
        def waiver(until: str) -> str:
            return with_waivers(waiver_item(until=f'"{until}"'))

        self.assertEqual(self.findings(waiver("2026-10-15")), ([], []))  # 15 days out: quiet
        errors, warnings = self.findings(waiver("2026-10-14"))  # 14 days out
        self.assertEqual(errors, [])
        self.assertTrue(any("expires on 2026-10-14" in w for w in warnings), warnings)
        errors, warnings = self.findings(waiver("2026-09-30"))  # the last day still counts
        self.assertEqual(errors, [])
        self.assertTrue(warnings)
        errors, _ = self.findings(waiver("2026-09-29"))
        self.assertTrue(any("expired on 2026-09-29" in e for e in errors), errors)

    def test_a_rule_past_its_review_date_warns(self):
        errors, warnings = self.findings(RULE + '      review_due: "2026-09-01"\n')
        self.assertEqual(errors, [])
        self.assertTrue(any("review_due 2026-09-01" in w and "r1" in w for w in warnings), warnings)
        self.assertEqual(self.findings(RULE + '      review_due: "2026-10-01"\n'), ([], []))

    def test_aidd_validate_reports_them(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / ".aidd" / "config.yaml"
            path.parent.mkdir()
            expired = (dt.date.today() - dt.timedelta(days=1)).isoformat()
            path.write_text(
                HEAD + with_waivers(waiver_item(who="agent:dev", until=f'"{expired}"'), rules=RULE + RULE_ITEM),
                encoding="utf-8",
            )
            code, out = run_cli("validate", str(path))
        self.assertEqual(code, 1, out)
        self.assertIn("unique", out)
        self.assertIn("a person approves a waiver", out)
        self.assertIn(f"expired on {expired}", out)

    def test_an_unknown_level_fails_validate(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / ".aidd" / "config.yaml"
            path.parent.mkdir()
            path.write_text(HEAD + RULE.replace("level: must", "level: required"), encoding="utf-8")
            code, out = run_cli("validate", str(path))
        self.assertEqual(code, 1, out)
        self.assertIn("level", out)


def spec_text(body: str, docs: str = "") -> str:
    return (
        '---\naidd_version: "1.0.0"\nkind: spec\nid: S-1\ntitle: t\nowner_team: core\ntype: feat\n'
        "route: normal\nconfidence: high\nassisted_by: []\nrollback: Revert.\n"
        "risk:\n  summary: s\n  dimensions: []\n  reversible: true\n"
        "tasks:\n  - id: S-1-T1\n    title: t\n    scope: [src/a.py]\n"
        "tests:\n  files: [tests/t.py]\n  commands:\n    - name: a\n      command: [pytest]\n      new_behavior: true\n"
        f"{docs}---\n\n## Intent\n\ni\n\n## Policy conflicts\n\nnone\n\n{body}\n\n## Acceptance\n\na\n"
    )


class HoldHintTests(unittest.TestCase):
    """A hint, never a gate rule: a Spec whose Context or Design names a `hold` technology without a linked ADR."""

    def warnings(self, text: str, adr: bool = False) -> list[str]:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q")
            (root / ".aidd").mkdir()
            (root / ".aidd" / "config.yaml").write_text(HEAD + "project:\n  stack:\n    adopt: [PostgreSQL]\n    hold: [MongoDB, Redux]\n", encoding="utf-8")
            if adr:
                (root / "docs" / "adr").mkdir(parents=True)
                (root / "docs" / "adr" / "0001-mongo.md").write_text("# S-1: MongoDB for events\n", encoding="utf-8")
            (root / "specs").mkdir()
            spec = root / "specs" / "S-1.md"
            spec.write_text(text, encoding="utf-8")
            return [e for e in validation.validate_file(spec) if "project.stack" in e]

    def test_a_hold_item_in_the_design_warns(self):
        found = self.warnings(spec_text("## Context\n\nEvents today.\n\n## Design\n\nStore events in mongodb collections."))
        self.assertEqual(len(found), 1, found)
        self.assertTrue(found[0].startswith("warning: "), found)
        self.assertIn("MongoDB", found[0])
        self.assertIn("ADR", found[0])

    def test_a_linked_adr_or_no_mention_is_quiet(self):
        adr = "docs:\n  - kind: adr\n    path: docs/adr/0001-mongo.md\n"
        self.assertEqual(self.warnings(spec_text("## Context\n\nc\n\n## Design\n\nUse MongoDB.", adr), adr=True), [])
        self.assertEqual(self.warnings(spec_text("## Context\n\nc\n\n## Design\n\nUse PostgreSQL; Reduxion is a name.")), [])
        # Only Context and Design are read: the Acceptance may name it.
        self.assertEqual(self.warnings(spec_text("## Context\n\nc\n\n## Design\n\nd\n\n## Out of scope\n\nMongoDB")), [])


class LayeringTests(unittest.TestCase):
    PARENT = (
        "locks: [project]\nproject:\n  hosting: EU only\n  stack:\n    adopt: [Python]\n    hold: [MongoDB]\n"
        "  budget:\n    max_infra_per_month: 100\n    currency: EUR\n    new_paid_service: ask\n"
        '  rules:\n    - id: eu-data\n      level: must\n      statement: Personal data stays in the EU.\n      why: GDPR.\n      owner: "@dpo"\n'
        '    - id: small-prs\n      level: should\n      statement: Keep PRs small.\n      why: Review quality.\n      owner: "@leads"\n'
    )

    def load(self, child: str, parent: str | None = None) -> config.Config:
        return config.load_text(HEAD + "extends: [{path: p.yaml}]\n" + child, prefetched={"p.yaml": HEAD + (parent or self.PARENT)})

    def rules(self, cfg: config.Config) -> dict[str, str]:
        return {r["id"]: r["level"] for r in cfg.get("project", "rules")}

    def test_a_child_adds_rules_and_tightens(self):
        cfg = self.load(
            'project:\n  rules:\n    - id: small-prs\n      level: must\n      statement: Keep PRs small.\n      why: Review quality.\n      owner: "@leads"\n'
            '    - id: own\n      level: may\n      statement: s\n      why: w\n      owner: "@me"\n'
            "  stack:\n    adopt: [htmx]\n    hold: [Redux]\n  budget:\n    max_infra_per_month: 40\n    currency: EUR\n    new_paid_service: forbidden\n"
        )
        self.assertEqual(self.rules(cfg), {"eu-data": "must", "small-prs": "must", "own": "may"})
        self.assertEqual(cfg.get("project", "stack", "adopt"), ["Python", "htmx"])
        self.assertEqual(cfg.get("project", "stack", "hold"), ["MongoDB", "Redux"])
        self.assertEqual(cfg.get("project", "budget"), {"max_infra_per_month": 40, "currency": "EUR", "new_paid_service": "forbidden"})
        self.assertEqual([w for w in cfg.warnings if "project" in w], [])

    def test_a_child_never_loosens_a_locked_parent(self):
        cfg = self.load(
            "project:\n  hosting: anywhere\n"
            '  rules:\n    - id: eu-data\n      level: may\n      statement: Whatever.\n      why: w\n      owner: "@me"\n'
            '  waivers:\n    - rule: eu-data\n      reason: r\n      approved_by: "@me"\n      until: "2099-01-01"\n'
            "  stack:\n    adopt: [MongoDB]\n  budget:\n    max_infra_per_month: 500\n    currency: EUR\n    new_paid_service: allowed\n"
        )
        self.assertEqual(self.rules(cfg), {"eu-data": "must", "small-prs": "should"})
        self.assertEqual(cfg.get("project", "rules")[0]["statement"], "Personal data stays in the EU.")
        self.assertEqual(cfg.get("project", "waivers", default=[]), [])
        self.assertNotIn("MongoDB", cfg.get("project", "stack", "adopt"))
        self.assertIn("MongoDB", cfg.get("project", "stack", "hold"))
        self.assertEqual(cfg.get("project", "budget"), {"max_infra_per_month": 100, "currency": "EUR", "new_paid_service": "ask"})
        self.assertEqual(cfg.get("project", "hosting"), "EU only")
        said = " ".join(w for w in cfg.warnings if "project" in w)
        for what in ("eu-data", "waiver", "MongoDB", "max_infra_per_month", "new_paid_service", "hosting"):
            self.assertIn(what, said, what)
        self.assertIn("project", cfg.get("locks"))

    def test_without_the_lock_a_child_may_replace(self):
        cfg = self.load(
            'project:\n  rules:\n    - id: eu-data\n      level: should\n      statement: Prefer the EU.\n      why: w\n      owner: "@me"\n'
            "  budget:\n    new_paid_service: allowed\n",
            parent=self.PARENT.replace("locks: [project]\n", ""),
        )
        self.assertEqual(self.rules(cfg)["eu-data"], "should")
        self.assertEqual(cfg.get("project", "budget", "new_paid_service"), "allowed")


class OutputTests(unittest.TestCase):
    def test_owners_prints_the_rules_for_the_changed_paths_must_first(self):
        r = owners.owners_view(load(), changed=["src/api/orders.py"])
        p = r["project"]
        self.assertEqual([x["id"] for x in p["rules"]], ["money-in-minor-units", "no-orm-raw-sql", "docs-voice"])
        self.assertEqual(p["rules"][1]["waiver"]["approved_by"], "@alice")
        elsewhere = owners.owners_view(load(), changed=["web/index.html"])["project"]
        self.assertEqual([x["id"] for x in elsewhere["rules"]], ["money-in-minor-units", "docs-voice"])
        text = owners.owners_markdown(r)
        self.assertIn("Stack: adopt Python, PostgreSQL; trial htmx; hold MongoDB", text)
        section = text.split("## Project constraints", 1)[1]
        self.assertLess(section.index("money-in-minor-units"), section.index("no-orm-raw-sql"))
        self.assertIn("Floats lose minor units on rounding.", section)
        self.assertIn("waived until 2099-12-31", section)
        self.assertIsNone(owners.owners_view(config.load_text(HEAD))["project"])
        self.assertNotIn("## Project constraints", owners.owners_markdown(owners.owners_view(config.load_text(HEAD))))

    def test_gate_paths_prints_them_for_the_planned_paths(self):
        with adopted_repo() as root:
            cfg = root / ".aidd" / "config.yaml"
            cfg.write_text(cfg.read_text(encoding="utf-8") + FULL, encoding="utf-8")
            git(root, "commit", "-qam", "constraints")
            code, out = run_cli("gate", "--paths", "src/api/orders.py")
            self.assertEqual(code, 0, out)
            self.assertIn("Stack: adopt Python, PostgreSQL; trial htmx; hold MongoDB", out)
            self.assertIn("MUST money-in-minor-units", out)
            self.assertIn("SHOULD no-orm-raw-sql", out)
            self.assertLess(out.index("money-in-minor-units"), out.index("no-orm-raw-sql"))
            self.assertIn("One place to review every query.", out)
            code, out = run_cli("gate", "--paths", "web/index.html", "--json")
            answer = json.loads(out)
            self.assertEqual([r["id"] for r in answer["project"]["rules"]], ["money-in-minor-units", "docs-voice"])
            code, out = run_cli("owners", "--changed", "src/api/orders.py")
            self.assertIn("no-orm-raw-sql", out)


class InitTests(unittest.TestCase):
    def test_init_prefills_the_radar_as_a_commented_block(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q", "-b", "main")
            (root / "pyproject.toml").write_text('[project]\nname = "x"\n[tool.pytest.ini_options]\n', encoding="utf-8")
            (root / "tests").mkdir()
            code, out = run_cli(
                "init", str(root), "--profile", "solo", "--approvers", "email:me@example.com", "--ci", "none", "--harness", "none", "--no-skill"
            )
            self.assertEqual(code, 0, out)
            text = (root / ".aidd" / "config.yaml").read_text(encoding="utf-8")
            self.assertIn("#   stack:\n#     adopt: [Python, pytest]\n", text)
            self.assertNotIn("\nproject:", text)  # commented: nothing binds until a person edits it
            self.assertNotIn("hosting:", text)
            self.assertNotIn("max_infra_per_month:", text)
            self.assertIsNone(config.load_file(".aidd/config.yaml", str(root)).get("project"))
            code, out = run_cli("validate", str(root / ".aidd" / "config.yaml"))
            self.assertEqual(code, 0, out)
            # Uncommented as written (the stack and the `project` line it sits under), the block is a valid `project.stack`.
            live = text.replace("# project:", "project:").replace("#   stack:", "  stack:").replace("#     adopt: ", "    adopt: ")
            self.assertEqual(config.load_text(live).get("project", "stack", "adopt"), ["Python", "pytest"])

    def test_no_detection_writes_no_block(self):
        self.assertNotIn("stack:", config_template.config_text(config_template.ConfigTemplate("solo", approvers=["@me"])))
        self.assertIn("#     adopt: [Go]", config_template.config_text(config_template.ConfigTemplate("solo", approvers=["@me"], stack=["Go"])))


if __name__ == "__main__":
    unittest.main()
