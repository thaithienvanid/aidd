"""The pack template and the practice template, enforced by `aidd eval packs`, and where each fact lives.

Every pack is generated in one template (Scope, Standards, Dated obligations, Checklist by loop step, Test commands,
Owned elsewhere, References, Keep it current) and every practice skill is written in another (Use it when and not when,
Standards generated from registry ids, the loop steps it works in, Test commands, Stop if, Hand off). A fact lives with
its owner and the others point to it: the product defaults, the shared scanners, the AI evals, the breach clocks, the
migrations, the accessibility and screenshot tests, and the build provenance.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT

from aidd.evals import standards_audit
from aidd.cli import app
from aidd.docsgen import pack_budget
from aidd.docsgen import token_caps
from aidd.docsgen import pack_render
from aidd.knowledge import role_text, standards_evidence, team_registry
from aidd.kernel import documents, json_schema, resources

TEAM = ROOT / "plugins" / "aidd-team"
SKILLS = TEAM / "skills"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def pack(slug: str) -> dict:
    return next(d for d in team_registry.roles()["domains"] if d["slug"] == slug)


def raw_pack(slug: str) -> dict:
    return next(d for d in resources.load_json("roles.json")["domains"] if d["slug"] == slug)


def eval_packs(*args: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = app.main(["eval", "packs", *args])
    return code, out.getvalue()


# ---------------------------------------------------------------------------------------------------------------
# A small, self-contained registry and skills folder, so each rule of the check is shown failing on its own.

STD = {"id": "s-one", "name": "Standard one", "release": "1.0", "checked": "2026-09-30", "source": "https://example.org/one"}
STD2 = {"id": "s-two", "name": "Standard two", "reviewed": "2026-09-30"}

PRACTICE = """---
name: p-one
description: "Practice skill: do one thing. Use in an aidd repository when a Task does it."
metadata:
  checked: "2026-09-30"
---

# P one

**Use it when** a Task does the thing.

**Do not use when** it does not.

## Standards

<!-- aidd:gen practice:p-one -->
<!-- aidd:end -->

## Implement

- Do it well.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Own test | it works | `run it` |

## Stop if

- It does not work.

## Hand off

- Done: it. Next: the reviewer. Needs: none. Stopped at: none.
"""


def fixture_pack(**over) -> dict:
    d = {
        "name": "Pack one",
        "slug": "pack-one",
        "signal": "the thing",
        "triggers": ["a", "b", "c", "d", "e"],
        "scope": {"not_when": "it does not", "neighbours": ["p-one"]},
        "standards": [dict(STD), dict(STD2)],
        "checklist": [
            {"step": "Specify", "item": "Name it.", "cites": ["s-one"]},
            {"step": "Implement", "item": "Build it.", "cites": ["s-two"]},
        ],
        "tests": [{"name": "Pack test", "proves": "it holds", "how": "`check it`", "cites": ["s-one"]}],
        "tests_elsewhere": [{"owner": "p-one", "tests": ["Own test"]}],
    }
    d.update(over)
    return d


class FixtureTests(unittest.TestCase):
    """Each rule of the template, broken on its own in a registry and a skills folder built for the test."""

    def run_check(self, domain: dict | None = None, practice: str = PRACTICE, practices: dict | None = None, refs: dict | None = None) -> list[str]:
        domain = domain or fixture_pack()
        data = {
            "order": ["dev"],
            "roles": {"dev": {"practices": ["p-one"], "standards": []}},
            "domains": [domain],
            "practices": {"p-one": {"standards": [dict(STD)]}} if practices is None else practices,
        }
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "p-one").mkdir()
            (folder / "p-one" / "SKILL.md").write_text(practice, encoding="utf-8")
            (folder / domain["slug"]).mkdir()
            for name, text in (refs or {}).items():
                (folder / domain["slug"] / "references").mkdir(exist_ok=True)
                (folder / domain["slug"] / "references" / name).write_text(text, encoding="utf-8")
            with mock.patch.object(team_registry, "roles", lambda: data):
                return [f"{p['where']}: {p['problem']}" for p in pack_budget.problems(folder)]

    def test_the_fixture_passes(self):
        self.assertEqual(self.run_check(), [])

    def test_a_pack_standard_no_row_or_test_cites_fails(self):
        d = fixture_pack(checklist=[{"step": "Specify", "item": "Name it.", "cites": ["s-one"]}])
        self.assertTrue(any("'s-two' is cited by no checklist row or test" in p for p in self.run_check(d)))

    def test_a_row_citing_a_standard_the_pack_does_not_list_fails(self):
        d = fixture_pack(checklist=[*fixture_pack()["checklist"], {"step": "Review", "item": "Look.", "cites": ["s-nine"]}])
        self.assertTrue(any("cites 's-nine', which the pack does not list" in p for p in self.run_check(d)))

    def test_too_many_rows_in_one_step_and_too_many_standards_and_tests_fail(self):
        rows = [{"step": "Specify", "item": f"Row {i}.", "cites": ["s-one", "s-two"]} for i in range(5)]
        stds = [dict(STD, id=f"s-{i}") for i in range(11)]
        tests = [{"name": f"T{i}", "proves": "x", "how": "y", "cites": [f"s-{i}"]} for i in range(9)]
        found = self.run_check(fixture_pack(checklist=rows))
        self.assertTrue(any("5 checklist rows at Specify" in p for p in found), found)
        found = self.run_check(fixture_pack(standards=stds, checklist=[{"step": "Specify", "item": "x", "cites": [s["id"] for s in stds]}], tests=tests))
        self.assertTrue(any("11 standards" in p for p in found), found)
        self.assertTrue(any("9 test commands" in p for p in found), found)

    def test_the_defaults_row_counts_toward_its_step(self):
        rows = [{"step": "Entry", "item": f"Row {i}.", "cites": ["s-one", "s-two"]} for i in range(4)]
        found = self.run_check(fixture_pack(checklist=rows, defaults=["dark_mode"]))
        self.assertTrue(any("5 checklist rows at Entry" in p for p in found), found)

    def test_a_long_scope_fails(self):
        d = fixture_pack(scope={"not_when": " ".join(["word"] * 60), "neighbours": ["p-one"]})
        self.assertTrue(any("the Scope is" in p for p in self.run_check(d)))

    def test_a_test_name_used_twice_across_packs_and_skills_fails(self):
        d = fixture_pack(tests=[{"name": "Own test", "proves": "x", "how": "y", "cites": ["s-one"]}], tests_elsewhere=None)
        d = {k: v for k, v in d.items() if v is not None}
        self.assertTrue(any("the test name 'Own test' is used 2 times" in p for p in self.run_check(d)))

    def test_a_pointer_to_a_test_its_owner_lacks_fails(self):
        d = fixture_pack(tests_elsewhere=[{"owner": "p-one", "tests": ["Missing test"]}])
        self.assertTrue(any("points to 'Missing test' in p-one" in p for p in self.run_check(d)))
        d = fixture_pack(tests_elsewhere=[{"owner": "no-such-skill", "tests": ["Own test"]}])
        self.assertTrue(any("'no-such-skill', which is no pack or practice skill" in p for p in self.run_check(d)))

    def test_a_practice_out_of_order_or_missing_a_section_fails(self):
        swapped = PRACTICE.replace("## Implement\n\n- Do it well.\n\n", "").replace("## Hand off", "## Implement\n\n- Do it well.\n\n## Hand off")
        self.assertTrue(any("out of the template's order" in p for p in self.run_check(practice=swapped)))
        self.assertTrue(any("no 'Stop if' section" in p for p in self.run_check(practice=PRACTICE.replace("## Stop if", "### Stop if"))))
        self.assertTrue(any("a heading the template does not have: 'Draw'" in p for p in self.run_check(practice=PRACTICE.replace("## Implement", "## Draw"))))
        self.assertTrue(any("no **Do not use when**" in p for p in self.run_check(practice=PRACTICE.replace("**Do not use when**", "Not"))))

    def test_practice_standards_come_from_the_registry(self):
        hand = PRACTICE.replace("<!-- aidd:gen practice:p-one -->\n<!-- aidd:end -->", "- Standard one, 1.0.")
        self.assertTrue(any("is not the generated block" in p for p in self.run_check(practice=hand)))
        self.assertTrue(any("no `practices` entry" in p for p in self.run_check(practices={})))

    def test_size_caps_fail(self):
        big = PRACTICE.replace("- Do it well.", "- " + "x" * 6500)
        self.assertTrue(any("SKILL.md is about" in p and "the cap is 1600" in p for p in self.run_check(practice=big)))
        refs = {"a.md": "x", "b.md": "y", "c.md": "z" * 6100}
        d = fixture_pack(references=[{"path": f"references/{n}", "holds": "it"} for n in refs])
        found = self.run_check(d, refs=refs)
        self.assertTrue(any("3 references; the template allows 2" in p for p in found), found)
        self.assertTrue(any("references/c.md is about 1525 tokens" in p for p in found), found)
        self.assertTrue(any("differ from the registry" in p for p in self.run_check(refs={"stray.md": "x"})))
        long_pack = fixture_pack(checklist=[*fixture_pack()["checklist"], {"step": "Review", "item": "y" * 8000, "cites": ["s-one"]}])
        self.assertTrue(any("the cap is 2200" in p for p in self.run_check(long_pack)))

    def test_a_business_pack_needs_its_terms_and_invariants(self):
        found = self.run_check(dict(fixture_pack(), kind="business"))
        self.assertTrue(any("a business pack with no `terms`" in p for p in found), found)
        self.assertTrue(any("a business pack with no `invariants`" in p for p in found), found)
        self.assertFalse(any("a business pack" in p for p in self.run_check(dict(fixture_pack(), kind="technology"))))

    def test_the_printed_caps_are_the_caps(self):
        from aidd.cli.commands import setup as setup_command
        from aidd.docsgen import pack_budget

        for cap in (token_caps.PACK_TOKENS, token_caps.PRACTICE_TOKENS, token_caps.REFERENCE_TOKENS, pack_budget.DESCRIPTION_CHARS):
            self.assertIn(f"{cap:,}", setup_command.PACKS_BASIS)

    def test_a_long_or_repeated_description_fails(self):
        """Every session lists every description, so each is short, and the config path is said once, in the aidd skill."""
        long = PRACTICE.replace("do one thing.", "do one thing. " + "y" * 200)
        found = self.run_check(practice=long)
        self.assertTrue(any(p.startswith("practice p-one: the description is") and "the cap is 250" in p for p in found), found)
        repeated = PRACTICE.replace("an aidd repository when", "an aidd repository (.aidd/config.yaml) when")
        found = self.run_check(practice=repeated)
        self.assertTrue(any("(.aidd/config.yaml)" in p and "practice p-one" in p for p in found), found)

    def test_the_estimate_is_four_characters_a_token(self):
        self.assertEqual(token_caps.estimate_tokens("x" * 4), 1)
        self.assertEqual(token_caps.estimate_tokens("x" * 5), 2)


class RepositoryTests(unittest.TestCase):
    """The shipped packs and practice skills meet both templates, and `aidd eval packs` says so."""

    def test_every_pack_and_practice_skill_meets_its_template(self):
        self.assertEqual(pack_budget.problems(), [])

    def test_the_cli_passes_and_reports_the_sizes(self):
        code, out = eval_packs()
        self.assertEqual(code, 0, out)
        self.assertIn(f"{len(team_registry.roles()['domains'])} packs: about", out)
        self.assertIn("0 problem(s)", out)
        # The descriptions every session lists: each skill's and each command's, with the total printed.
        listed = pack_budget.pack_descriptions()
        total = sum(d["chars"] for d in listed)
        self.assertIn(f"{len(listed)} descriptions: {total:,} characters in all", out)
        self.assertEqual({d["name"] for d in listed if d["kind"] == "command"}, {p.stem for p in (ROOT / "plugins/aidd-team/commands").glob("*.md")})
        self.assertLessEqual({"aidd", "aidd-team", *role_text.practice_names()}, {d["name"] for d in listed if d["kind"] == "skill"})
        for d in listed:
            self.assertLessEqual(d["chars"], pack_budget.ROUTER_DESCRIPTION_CHARS if d["name"] == "aidd-team" else pack_budget.DESCRIPTION_CHARS, d["name"])
        code, out = eval_packs("--json")
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(json_schema.validate(report, "packs.schema.json"), [])
        self.assertEqual(report["schema_version"], "1")
        self.assertEqual(report["problems"], [])
        self.assertEqual(report["descriptions"], listed)
        names = {s["name"] for s in report["sizes"]}
        self.assertLessEqual({d["slug"] for d in team_registry.roles()["domains"]} | set(role_text.practice_names()), names)

    def test_the_cli_fails_on_a_problem(self):
        with mock.patch.object(pack_budget, "pack_sizes_and_problems", lambda folder=None: ([], [{"where": "pack x", "problem": "broken"}])):
            code, out = eval_packs()
        self.assertEqual(code, 1)
        self.assertIn("[!!] pack x: broken", out)

    def test_a_pack_renders_the_template_in_order(self):
        for d in team_registry.roles()["domains"]:
            text = pack_render.render_pack(d)
            found = pack_budget.headings(text)
            self.assertEqual(found, [h for h in pack_render.PACK_SECTIONS if h in found], d["slug"])
            # A business pack names its words before its standards; every pack opens with its Scope.
            self.assertEqual(found[:2], ["Scope", "Terms" if d.get("kind") == "business" else "Standards"], d["slug"])
            self.assertEqual("Invariants and missed cases" in found, d.get("kind") == "business", d["slug"])
            self.assertEqual(found[-1], "Keep it current", d["slug"])
            self.assertEqual(len(documents.raw_section(text, "Keep it current").strip().splitlines()), 1, d["slug"])
            self.assertNotIn("(published ", documents.raw_section(text, "Standards"), d["slug"])

    def test_every_checklist_row_names_its_standard(self):
        for d in team_registry.roles()["domains"]:
            text = documents.raw_section(pack_render.render_pack(d), "Checklist by loop step")
            rows = [r for r in text.splitlines() if r.startswith("| ") and not r.startswith(("| Step", "| ---"))]
            for row in rows:
                cell = row.rstrip(" |").rsplit(" | ", 1)[1]
                self.assertRegex(cell, r"^(S\d+(, S\d+)*|—)$", (d["slug"], row[:60]))
                if cell == "—":
                    self.assertIn("aidd-team:product-defaults", row, d["slug"])

    def test_only_regulated_or_platform_packs_have_dated_obligations(self):
        dated = {d["slug"] for d in team_registry.roles()["domains"] if d.get("obligations")}
        # Regulated and platform packs only: their duties apply from dates a team must plan around.
        self.assertEqual(
            dated,
            {
                "ai-features",
                "payments-and-finance",
                "public-sector",
                "package-publishing",
                "extensions-and-marketplace-apps",
                "mobile-apps",
                "desktop-apps",
                "embedded-automotive-industrial",
                "products-for-children",
                "health",
                "commerce-and-marketplaces",
                "education",
                "hr-and-workforce",
            },
        )


class PracticeStandardsTests(unittest.TestCase):
    """A practice skill's standards are registry ids, rendered by `aidd gen-docs`, so each edition is checked."""

    def test_every_practice_has_registry_standards_rendered_in_its_skill(self):
        data = team_registry.roles()
        self.assertEqual(set(data["practices"]), set(role_text.practice_names()))
        for name in role_text.practice_names():
            text = read(SKILLS / name / "SKILL.md")
            block = re.search(rf"<!-- aidd:gen practice:{name} -->\n(.*?)<!-- aidd:end -->", text, re.S)
            self.assertIsNotNone(block, name)
            self.assertEqual(block.group(1), pack_render.practice_standards(name) + "\n", name)
            for s in data["practices"][name]["standards"]:
                self.assertIn(f"| {s['name']}", block.group(1), (name, s["id"]))

    def test_the_currency_check_reads_each_practice_standard(self):
        where = {(s.get("id"), s["where"]) for s in standards_evidence.dated_entries()}
        for name, entry in team_registry.roles()["practices"].items():
            for s in entry["standards"]:
                self.assertIn((s["id"], f"practice {name}"), where)

    def test_every_referenced_id_exists_and_every_entry_is_used(self):
        raw = resources.load_json("roles.json")
        used = set()
        refs = [r for role in raw["roles"].values() for r in role["standards"]]
        refs += [r for d in raw["domains"] for r in d["standards"]]
        refs += [r for p in raw["practices"].values() for r in p["standards"]]
        for r in refs:
            sid = r if isinstance(r, str) else r["id"]
            self.assertIn(sid, raw["standards"])
            used.add(sid)
        self.assertEqual(set(raw["standards"]) - used, set())


class DedupTests(unittest.TestCase):
    """One owner per fact; the others point to it."""

    def test_product_defaults_own_every_default(self):
        for slug in ("web-front-end", "apis-and-services", "internationalization"):
            d = raw_pack(slug)
            self.assertTrue(d["defaults"], slug)
            for c in d["checklist"]:
                self.assertNotRegex(c["item"], r"\(`(dark_mode|responsive|perf_budget|api_conventions|data_conventions|operability|security_headers)`\)", slug)
        self.assertFalse((SKILLS / "web-front-end" / "references").exists())
        self.assertTrue((SKILLS / "product-defaults" / "references" / "web.md").is_file())
        for name in ("api-design", "observability", "secure-coding", "ci-pipeline"):
            self.assertNotIn("## Product defaults", read(SKILLS / name / "SKILL.md"), name)
        tests = pack_budget.practice_tests(read(SKILLS / "product-defaults" / "SKILL.md"))
        for name in ("Performance budget", "Both themes", "Responsive and targets", "Security headers", "API conventions", "Operability smoke", "Dev basics"):
            self.assertIn(name, tests)

    def test_enterprise_controls_own_the_pinned_scanners(self):
        own = {t["name"]: t["how"] for t in pack("enterprise-controls")["tests"]}
        self.assertIn("osv-scanner@v", own["Dependency scan"])
        self.assertIn("semgrep==", own["Static analysis"])
        self.assertRegex(own["Secret scan"], r"gitleaks v\d")
        self.assertRegex(own["Container scan and SBOM"], r"Trivy v\d.*Syft v\d")
        for d in team_registry.roles()["domains"]:
            if d["slug"] == "enterprise-controls":
                continue
            for t in d["tests"]:
                self.assertNotRegex(t["how"].lower(), r"osv-scanner|gitleaks|pip-audit|npm audit|grype|syft", (d["slug"], t["name"]))
        secure = read(SKILLS / "secure-coding" / "SKILL.md")
        self.assertIn("From `aidd-team:enterprise-controls`: Dependency scan, Static analysis, Secret scan", secure)

    def test_ai_eval_tests_live_in_ai_evals(self):
        self.assertEqual(pack("ai-features")["tests"], [])
        self.assertEqual(
            pack("ai-features")["tests_elsewhere"],
            [{"owner": "ai-evals", "tests": ["Eval suite", "Regression evals", "Injection probes", "Cost and latency budget", "Output PII scan"]}],
        )
        self.assertIn({"owner": "ai-evals", "tests": ["Injection probes"]}, pack("ai-agents-and-tools")["tests_elsewhere"])

    def test_the_breach_clocks_are_one_table_in_incident_response(self):
        text = read(SKILLS / "incident-response" / "SKILL.md") + "".join(read(p) for p in (SKILLS / "incident-response" / "references").glob("*.md"))
        for regime in ("GDPR", "CRA", "NIS2", "DORA", "HIPAA", "SEC", "24 h", "72 h", "14 d", "60 calendar days", "four business days"):
            self.assertIn(regime, text, regime)
        for d in team_registry.roles()["domains"]:
            self.assertNotIn("72 hours", pack_render.render_pack(d), d["slug"])
        for slug in ("privacy-by-default", "payments-and-finance", "health", "enterprise-controls"):
            owners = [x["owner"] for x in raw_pack(slug).get("owned_elsewhere", [])]
            self.assertIn("incident-response", owners, slug)

    def test_migrations_plans_and_transfers_have_one_owner(self):
        data = raw_pack("data-and-analytics")
        owners = {x["owner"] for x in data["owned_elsewhere"]}
        self.assertEqual(owners, {"schema-migration", "performance", "privacy-by-default"})
        ids = {r if isinstance(r, str) else r["id"] for r in data["standards"]}
        self.assertNotIn("cross-border-transfers-the-mechanism-a", ids)
        self.assertIn("cross-border-transfers-the-mechanism-a", {r if isinstance(r, str) else r["id"] for r in raw_pack("privacy-by-default")["standards"]})

    def test_axe_and_screenshots_have_one_owner(self):
        for d in team_registry.roles()["domains"]:
            for t in d["tests"]:
                self.assertNotIn("axe", t["how"].lower(), (d["slug"], t["name"]))
                self.assertNotIn("toHaveScreenshot", t["how"], (d["slug"], t["name"]))
        proto = read(SKILLS / "prototyping" / "SKILL.md")
        row = next(r for r in documents.raw_section(proto, "Test commands").splitlines() if r.startswith("| Screenshot matrix"))
        self.assertIn("toHaveScreenshot", row)
        self.assertIn("tests.files", row)
        self.assertIn("Accessibility per state", pack_budget.practice_tests(read(SKILLS / "accessible-ui" / "SKILL.md")))

    def test_build_provenance_moved_from_the_cloud_pack(self):
        cloud = {r if isinstance(r, str) else r["id"] for r in raw_pack("cloud-and-infrastructure")["standards"]}
        moved = {"slsa", "openssf-scorecard", "openssf-open-source-project-security-baseline"}
        self.assertEqual(cloud & moved, set())
        # The pipeline keeps build provenance; a published project's Scorecard and OSPS Baseline are package-publishing's.
        ci = {r if isinstance(r, str) else r["id"] for r in resources.load_json("roles.json")["practices"]["ci-pipeline"]["standards"]}
        self.assertIn("slsa", ci)
        published = {r if isinstance(r, str) else r["id"] for r in raw_pack("package-publishing")["standards"]}
        self.assertLessEqual(moved, published)


class ContradictionTests(unittest.TestCase):
    """Four facts that two pages once stated differently, each with one owner now."""

    IAC = (
        "CI/CD files are protected paths (major, the security pool); IaC, containers, and Kubernetes manifests are baseline rules "
        "(normal) unless a dimension, a risk rule, or a protected path raises them."
    )

    def test_one_statement_of_the_iac_route_matching_the_baseline(self):
        base = resources.load_json("baseline.json")
        rules = {r["name"]: r for r in base["risk_rules"]}
        self.assertEqual(rules["baseline:iac"]["route"], "normal")
        self.assertEqual(rules["baseline:containers"]["route"], "normal")
        self.assertIn(".github/workflows/**", base["protected_paths"])
        self.assertIn(self.IAC, [c["item"] for c in pack("cloud-and-infrastructure")["checklist"]])
        ci = read(SKILLS / "ci-pipeline" / "SKILL.md")
        self.assertIn(self.IAC, " ".join(ci.split()))
        self.assertNotIn("expect major and the security pool", ci)

    def test_the_design_review_is_pass_fail_with_proof_and_no_score(self):
        for path in (SKILLS / "prototyping" / "SKILL.md", SKILLS / "prototyping" / "references" / "design-review.md"):
            text = read(path)
            self.assertIn("pass/fail", text, path.name)
            self.assertIn("proof", text, path.name)
            self.assertRegex(text, r"(?i)no(?:t a|ver a)? (?:numeric )?score|never a numeric score", path.name)

    def test_mobile_accessibility_is_automated(self):
        text = read(SKILLS / "accessible-ui" / "SKILL.md")
        row = next(r for r in documents.raw_section(text, "Test commands").splitlines() if r.startswith("| Mobile accessibility checks"))
        self.assertIn("performAccessibilityAudit", row)
        self.assertIn("AccessibilityChecks", row)
        mobile = pack_render.render_pack(pack("mobile-apps"))
        self.assertNotIn("Accessibility Inspector", mobile)
        self.assertIn("Mobile accessibility checks", mobile)

    def test_the_idempotency_key_draft_is_marked_expired(self):
        entry = resources.load_json("roles.json")["standards"]["idempotency-keys-and-rate-limits"]
        self.assertIn("expired", entry["notes"])
        self.assertIn("2026-04-18", entry["notes"])
        self.assertIn("expired", read(SKILLS / "api-design" / "SKILL.md"))


class RegistryHygieneTests(unittest.TestCase):
    def setUp(self):
        self.table = resources.load_json("roles.json")["standards"]

    def test_ccpa_cpra_is_its_own_entry_sourced_from_the_agency(self):
        self.assertNotIn("gdpr-and-ccpa", self.table)
        entry = self.table["ccpa-cpra"]
        self.assertTrue(entry["source"].startswith("https://cppa.ca.gov/"), entry["source"])
        self.assertIn("cppa.ca.gov", entry["evidence"]["url"])
        self.assertTrue(standards_audit.confirms(entry))

    def test_editions_carry_no_history(self):
        for sid, e in self.table.items():
            edition = e.get("edition", "")
            self.assertNotRegex(edition, r"(?i)\bcurrent\b|replaced|which absorbs|first edition|second edition|corrected|consultation closed|Class D", sid)

    def test_one_mcp_entry_with_no_aidd_internals(self):
        self.assertNotIn("model-context-protocol-and-agent2agent-a2a", self.table)
        self.assertEqual([k for k, e in self.table.items() if "Model Context Protocol" in e["name"]], ["mcp-specification"])
        self.assertNotIn("`aidd mcp`", json.dumps(self.table))
        self.assertNotIn("aidd mcp", read(SKILLS / "ai-agents-and-tools" / "SKILL.md"))

    def test_fedramp_rev5_stays_active_to_at_least_2028(self):
        rev5 = self.table["fedramp-rev-5-baselines-where-they"]
        self.assertIn("2028-12-31", rev5["notes"])
        self.assertIn("December 31, 2028", rev5["evidence"]["quote"])
        dates = {o["date"] for o in pack("public-sector")["obligations"]}
        self.assertLessEqual({"2027-06-11", "2028-12-31"}, dates)

    def test_no_decorative_standard_is_left(self):
        for sid in (
            "owasp-agentic-skills-top-10-ast01",
            "data-mesh-principles",
            "dimensional-modelling-for-the-warehouse-bus",
            "eu-data-act",
            "software-carbon-intensity-a-rate-not",
        ):
            self.assertNotIn(sid, self.table)

    def test_every_edited_or_new_checked_entry_has_evidence_from_its_day(self):
        for sid, e in self.table.items():
            if e.get("checked") == "2026-09-30":
                self.assertEqual(e["evidence"]["retrieved"], "2026-09-30", sid)
                self.assertTrue(standards_audit.confirms(e), sid)


class BudgetTests(unittest.TestCase):
    """The templates made the knowledge smaller, not larger."""

    def test_the_skills_fit_their_caps(self):
        sizes, _ = pack_budget.pack_sizes_and_problems()
        for s in sizes:
            cap = token_caps.PACK_TOKENS if s["kind"] == "pack" else token_caps.PRACTICE_TOKENS
            self.assertLessEqual(s["tokens"], cap, s["name"])
            self.assertLessEqual(max(s["references"].values(), default=0), token_caps.REFERENCE_TOKENS, s["name"])

    def test_a_pack_copy_is_not_edited_by_hand(self):
        data = copy.deepcopy(team_registry.roles())
        for d in data["domains"]:
            self.assertEqual(read(pack_render.pack_path(ROOT, d)), pack_render.render_pack(d), d["slug"])


if __name__ == "__main__":
    unittest.main()
