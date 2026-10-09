"""The project's constraints and rules: `[project]` in .aidd/config.toml, a technology radar, hosting, a budget, the
team's own rules with their why, and waivers a person approves. `aidd validate` checks them, `aidd assess` and
`aidd owners` print the ones that apply, and `aidd init` pre-fills the radar from what it detects."""

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from helpers import adopted_repo, git, run_cli

from aidd import config, owners, project, repo

HEAD = 'aidd_version = "1.0.0"\nprofile = "team"\nowners = { approvers = ["@org/leads"] }\n'
TODAY = dt.date(2026, 9, 30)

FULL = """
[project]
hosting = "one VPS in the EU"

[project.stack]
adopt = ["Python", "PostgreSQL"]
trial = ["htmx"]
hold = ["MongoDB"]

[project.budget]
max_infra_per_month = 50
currency = "EUR"
new_paid_service = "ask"

[[project.rules]]
id = "no-orm-raw-sql"
level = "should"
statement = "Query through the repository layer, not raw SQL in handlers."
why = "One place to review every query."
applies = ["src/api/**"]
check = "lint"
source = "docs/adr/0003-repository-layer.md"
owner = "@org/leads"
review_due = 2027-03-01

[[project.rules]]
id = "money-in-minor-units"
level = "must"
statement = "Store money as an integer count of the currency's minor unit."
why = "Floats lose minor units on rounding."
owner = "@alice"

[[project.rules]]
id = "docs-voice"
level = "may"
statement = "Write docs in the second person."
why = "It reads as instructions."
owner = "@bob"

[[project.waivers]]
rule = "no-orm-raw-sql"
reason = "The reporting query needs a window function the layer lacks."
approved_by = "@alice"
until = 2099-12-31
"""


def load(extra: str = FULL) -> config.Config:
    return config.load_text(HEAD + extra)


def invalid(extra: str) -> bool:
    try:
        load(extra)
    except config.ConfigError:
        return True
    return False


RULE = '[[project.rules]]\nid = "r1"\nlevel = "must"\nstatement = "s"\nwhy = "w"\nowner = "@a"\n'


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
            "unknown level": RULE.replace('"must"', '"shall"'),
            "no why": RULE.replace('why = "w"\n', ""),
            "no owner": RULE.replace('owner = "@a"\n', ""),
            "no statement": RULE.replace('statement = "s"\n', ""),
            "id with spaces": RULE.replace('"r1"', '"r 1"'),
            "absolute applies": RULE + 'applies = ["/etc/**"]\n',
            "empty check": RULE + 'check = ""\n',
            "bad review_due": RULE + 'review_due = "soon"\n',
            "source with wildcard": RULE + 'source = "docs/adr/*.md"\n',
            "unknown rule key": RULE + 'severity = "high"\n',
            "unknown paid switch": '[project.budget]\nnew_paid_service = "sometimes"\n',
            "negative budget": '[project.budget]\nmax_infra_per_month = -1\ncurrency = "EUR"\n',
            "budget without currency": "[project.budget]\nmax_infra_per_month = 10\n",
            "lower-case currency": '[project.budget]\nmax_infra_per_month = 10\ncurrency = "eur"\n',
            "empty stack item": '[project.stack]\nadopt = [""]\n',
            "repeated stack item": '[project.stack]\nadopt = ["Go", "Go"]\n',
            "unknown ring": '[project.stack]\nassess = ["Rust"]\n',
            "empty hosting": '[project]\nhosting = ""\n',
            "unknown project key": "[project]\nteam_size = 3\n",
            "waiver without until": '[[project.waivers]]\nrule = "r1"\nreason = "r"\napproved_by = "@a"\n',
            "waiver without reason": '[[project.waivers]]\nrule = "r1"\napproved_by = "@a"\nuntil = 2026-10-01\n',
            "waiver with a bad date": '[[project.waivers]]\nrule = "r1"\nreason = "r"\napproved_by = "@a"\nuntil = "next week"\n',
        }
        for name, extra in bad.items():
            with self.subTest(name):
                self.assertTrue(invalid(extra), name)
        self.assertFalse(invalid(RULE))
        self.assertFalse(invalid('[project.budget]\nnew_paid_service = "forbidden"\n'))


class FindingTests(unittest.TestCase):
    def findings(self, extra: str, today: dt.date = TODAY):
        return project.findings(load(extra), today)

    def test_a_valid_project_has_no_findings(self):
        self.assertEqual(self.findings(FULL), ([], []))

    def test_duplicate_rule_ids_are_an_error(self):
        errors, _ = self.findings(RULE + RULE.replace('"must"', '"should"'))
        self.assertTrue(any("r1" in e and "unique" in e for e in errors), errors)

    def test_a_waiver_of_an_unknown_rule_is_an_error(self):
        errors, _ = self.findings(RULE + '[[project.waivers]]\nrule = "r2"\nreason = "r"\napproved_by = "@a"\nuntil = 2027-01-01\n')
        self.assertTrue(any("'r2'" in e and "no rule" in e for e in errors), errors)

    def test_a_waiver_approved_by_an_agent_or_a_bot_is_an_error(self):
        for who in ("agent:developer", "claude[bot]", "@codex-agent", "acme:agent:developer"):
            extra = '[identities]\nbots = ["codex-agent"]\n' + RULE
            extra += f'[[project.waivers]]\nrule = "r1"\nreason = "r"\napproved_by = "{who}"\nuntil = 2027-01-01\n'
            with self.subTest(who):
                errors, _ = self.findings(extra)
                self.assertTrue(any("a person approves a waiver" in e for e in errors), errors)

    def test_a_waiver_warns_two_weeks_before_it_expires_and_fails_once_expired(self):
        def waiver(until: str) -> str:
            return RULE + f'[[project.waivers]]\nrule = "r1"\nreason = "r"\napproved_by = "@a"\nuntil = {until}\n'

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
        errors, warnings = self.findings(RULE + "review_due = 2026-09-01\n")
        self.assertEqual(errors, [])
        self.assertTrue(any("review_due 2026-09-01" in w and "r1" in w for w in warnings), warnings)
        self.assertEqual(self.findings(RULE + "review_due = 2026-10-01\n"), ([], []))

    def test_aidd_validate_reports_them(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / ".aidd" / "config.toml"
            path.parent.mkdir()
            expired = (dt.date.today() - dt.timedelta(days=1)).isoformat()
            path.write_text(
                HEAD + RULE + RULE + f'[[project.waivers]]\nrule = "r1"\nreason = "r"\napproved_by = "agent:dev"\nuntil = {expired}\n',
                encoding="utf-8",
            )
            code, out = run_cli("validate", str(path))
        self.assertEqual(code, 1, out)
        self.assertIn("unique", out)
        self.assertIn("a person approves a waiver", out)
        self.assertIn(f"expired on {expired}", out)

    def test_an_unknown_level_fails_validate(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / ".aidd" / "config.toml"
            path.parent.mkdir()
            path.write_text(HEAD + RULE.replace('"must"', '"required"'), encoding="utf-8")
            code, out = run_cli("validate", str(path))
        self.assertEqual(code, 1, out)
        self.assertIn("level", out)


def spec_text(body: str, docs: str = "") -> str:
    return (
        '+++\naidd_version = "1.0.0"\nkind = "spec"\nid = "S-1"\ntitle = "t"\nowner_team = "core"\ntype = "feat"\n'
        'route = "normal"\nconfidence = "high"\nassisted_by = []\nrollback = "Revert."\n'
        '[risk]\nsummary = "s"\ndimensions = []\nreversible = true\n'
        '[[tasks]]\nid = "S-1-T1"\ntitle = "t"\nscope = ["src/a.py"]\n'
        '[tests]\nfiles = ["tests/t.py"]\n[[tests.commands]]\nname = "a"\ncommand = ["pytest"]\nnew_behavior = true\n'
        f"{docs}+++\n\n## Intent\n\ni\n\n## Policy conflicts\n\nnone\n\n{body}\n\n## Acceptance\n\na\n"
    )


class HoldHintTests(unittest.TestCase):
    """A hint, never a gate rule: a Spec whose Context or Design names a `hold` technology without a linked ADR."""

    def warnings(self, text: str, adr: bool = False) -> list[str]:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q")
            (root / ".aidd").mkdir()
            (root / ".aidd" / "config.toml").write_text(HEAD + '[project.stack]\nadopt = ["PostgreSQL"]\nhold = ["MongoDB", "Redux"]\n', encoding="utf-8")
            if adr:
                (root / "docs" / "adr").mkdir(parents=True)
                (root / "docs" / "adr" / "0001-mongo.md").write_text("# S-1: MongoDB for events\n", encoding="utf-8")
            (root / "specs").mkdir()
            spec = root / "specs" / "S-1.md"
            spec.write_text(text, encoding="utf-8")
            return [e for e in repo.validate_file(spec) if "project.stack" in e]

    def test_a_hold_item_in_the_design_warns(self):
        found = self.warnings(spec_text("## Context\n\nEvents today.\n\n## Design\n\nStore events in mongodb collections."))
        self.assertEqual(len(found), 1, found)
        self.assertTrue(found[0].startswith("warning: "), found)
        self.assertIn("MongoDB", found[0])
        self.assertIn("ADR", found[0])

    def test_a_linked_adr_or_no_mention_is_quiet(self):
        adr = '[[docs]]\nkind = "adr"\npath = "docs/adr/0001-mongo.md"\n'
        self.assertEqual(self.warnings(spec_text("## Context\n\nc\n\n## Design\n\nUse MongoDB.", adr), adr=True), [])
        self.assertEqual(self.warnings(spec_text("## Context\n\nc\n\n## Design\n\nUse PostgreSQL; Reduxion is a name.")), [])
        # Only Context and Design are read: the Acceptance may name it.
        self.assertEqual(self.warnings(spec_text("## Context\n\nc\n\n## Design\n\nd\n\n## Out of scope\n\nMongoDB")), [])


class LayeringTests(unittest.TestCase):
    PARENT = (
        'locks = ["project"]\n[project]\nhosting = "EU only"\n[project.stack]\nadopt = ["Python"]\nhold = ["MongoDB"]\n'
        '[project.budget]\nmax_infra_per_month = 100\ncurrency = "EUR"\nnew_paid_service = "ask"\n'
        '[[project.rules]]\nid = "eu-data"\nlevel = "must"\nstatement = "Personal data stays in the EU."\nwhy = "GDPR."\nowner = "@dpo"\n'
        '[[project.rules]]\nid = "small-prs"\nlevel = "should"\nstatement = "Keep PRs small."\nwhy = "Review quality."\nowner = "@leads"\n'
    )

    def load(self, child: str, parent: str | None = None) -> config.Config:
        return config.load_text(HEAD + 'extends = [{ path = "p.toml" }]\n' + child, prefetched={"p.toml": HEAD + (parent or self.PARENT)})

    def rules(self, cfg: config.Config) -> dict[str, str]:
        return {r["id"]: r["level"] for r in cfg.get("project", "rules")}

    def test_a_child_adds_rules_and_tightens(self):
        cfg = self.load(
            '[[project.rules]]\nid = "small-prs"\nlevel = "must"\nstatement = "Keep PRs small."\nwhy = "Review quality."\nowner = "@leads"\n'
            '[[project.rules]]\nid = "own"\nlevel = "may"\nstatement = "s"\nwhy = "w"\nowner = "@me"\n'
            '[project.stack]\nadopt = ["htmx"]\nhold = ["Redux"]\n[project.budget]\nmax_infra_per_month = 40\ncurrency = "EUR"\nnew_paid_service = "forbidden"\n'
        )
        self.assertEqual(self.rules(cfg), {"eu-data": "must", "small-prs": "must", "own": "may"})
        self.assertEqual(cfg.get("project", "stack", "adopt"), ["Python", "htmx"])
        self.assertEqual(cfg.get("project", "stack", "hold"), ["MongoDB", "Redux"])
        self.assertEqual(cfg.get("project", "budget"), {"max_infra_per_month": 40, "currency": "EUR", "new_paid_service": "forbidden"})
        self.assertEqual([w for w in cfg.warnings if "project" in w], [])

    def test_a_child_never_loosens_a_locked_parent(self):
        cfg = self.load(
            '[project]\nhosting = "anywhere"\n'
            '[[project.rules]]\nid = "eu-data"\nlevel = "may"\nstatement = "Whatever."\nwhy = "w"\nowner = "@me"\n'
            '[[project.waivers]]\nrule = "eu-data"\nreason = "r"\napproved_by = "@me"\nuntil = 2099-01-01\n'
            '[project.stack]\nadopt = ["MongoDB"]\n[project.budget]\nmax_infra_per_month = 500\ncurrency = "EUR"\nnew_paid_service = "allowed"\n'
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
            '[[project.rules]]\nid = "eu-data"\nlevel = "should"\nstatement = "Prefer the EU."\nwhy = "w"\nowner = "@me"\n'
            '[project.budget]\nnew_paid_service = "allowed"\n',
            parent=self.PARENT.replace('locks = ["project"]\n', ""),
        )
        self.assertEqual(self.rules(cfg)["eu-data"], "should")
        self.assertEqual(cfg.get("project", "budget", "new_paid_service"), "allowed")


class OutputTests(unittest.TestCase):
    def test_owners_prints_the_rules_for_the_changed_paths_must_first(self):
        r = owners.build(load(), changed=["src/api/orders.py"])
        p = r["project"]
        self.assertEqual([x["id"] for x in p["rules"]], ["money-in-minor-units", "no-orm-raw-sql", "docs-voice"])
        self.assertEqual(p["rules"][1]["waiver"]["approved_by"], "@alice")
        elsewhere = owners.build(load(), changed=["web/index.html"])["project"]
        self.assertEqual([x["id"] for x in elsewhere["rules"]], ["money-in-minor-units", "docs-voice"])
        text = owners.markdown(r)
        self.assertIn("Stack: adopt Python, PostgreSQL; trial htmx; hold MongoDB", text)
        section = text.split("## Project constraints", 1)[1]
        self.assertLess(section.index("money-in-minor-units"), section.index("no-orm-raw-sql"))
        self.assertIn("Floats lose minor units on rounding.", section)
        self.assertIn("waived until 2099-12-31", section)
        self.assertIsNone(owners.build(config.load_text(HEAD))["project"])
        self.assertNotIn("## Project constraints", owners.markdown(owners.build(config.load_text(HEAD))))

    def test_assess_prints_them_for_the_planned_paths(self):
        with adopted_repo() as root:
            cfg = root / ".aidd" / "config.toml"
            cfg.write_text(cfg.read_text(encoding="utf-8") + FULL, encoding="utf-8")
            git(root, "commit", "-qam", "constraints")
            code, out = run_cli("assess", "--paths", "src/api/orders.py")
            self.assertEqual(code, 0, out)
            self.assertIn("Stack: adopt Python, PostgreSQL; trial htmx; hold MongoDB", out)
            self.assertIn("MUST money-in-minor-units", out)
            self.assertIn("SHOULD no-orm-raw-sql", out)
            self.assertLess(out.index("money-in-minor-units"), out.index("no-orm-raw-sql"))
            self.assertIn("One place to review every query.", out)
            code, out = run_cli("assess", "--paths", "web/index.html", "--json")
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
            text = (root / ".aidd" / "config.toml").read_text(encoding="utf-8")
            self.assertIn("# [project.stack]", text)
            self.assertIn('# adopt = ["Python", "pytest"]', text)
            self.assertNotIn("\n[project", text)  # commented: nothing binds until a person edits it
            self.assertNotIn("hosting =", text)
            self.assertNotIn("max_infra_per_month =", text)
            self.assertIsNone(config.load_file(".aidd/config.toml", str(root)).get("project"))
            code, out = run_cli("validate", str(root / ".aidd" / "config.toml"))
            self.assertEqual(code, 0, out)
            # Uncommented as written, the block is a valid [project.stack].
            live = text.replace("# [project.stack]", "[project.stack]").replace("# adopt = ", "adopt = ")
            self.assertEqual(config.load_text(live).get("project", "stack", "adopt"), ["Python", "pytest"])

    def test_no_detection_writes_no_block(self):
        self.assertNotIn("[project.stack]", repo.config_text("solo", approvers=["@me"]))
        self.assertIn('# adopt = ["Go"]', repo.config_text("solo", approvers=["@me"], stack=["Go"]))


if __name__ == "__main__":
    unittest.main()
