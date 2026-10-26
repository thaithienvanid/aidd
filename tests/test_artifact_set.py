"""The artifact set. Testing lives in the Spec's Acceptance and the tech spec's Test strategy; a separate test plan,
a migration plan, and a tracking plan are asked for only when their trigger fires; a design spec, API, SLO, compliance,
and acceptance templates, the Initiative's brief, and the contract and change-order family; and a ceremony table that
keeps a solo founder near zero.
"""

import json
import re
import shutil
import unittest

from helpers import ROOT, RepoTemplateCase, aidd_subprocess, make_repo
from test_linked_docs import DOC, errors, spec_text, warnings

from aidd.workitems import validation
from aidd.workitems import spec_warnings
from aidd.workitems import authoring
from aidd import config
from aidd.workitems import spec_file
from aidd.kernel import documents, json_schema, resources
from aidd.knowledge import team_registry

SKILL = ROOT / ".agents" / "skills" / "aidd"
ASSETS = SKILL / "assets"
PROTOTYPING = ROOT / "plugins" / "aidd-team" / "skills" / "prototyping" / "SKILL.md"
NEW_KINDS = ("analytics", "migration", "acceptance")


def read(path) -> str:
    return path.read_text(encoding="utf-8")


def asset(name: str) -> str:
    return read(ASSETS / name)


def cfg(profile: str = "team"):
    approvers = '["@x", "@y"]' if profile == "audited" else '["@x"]'
    return config.load_text(f'aidd_version: "1.0.0"\nprofile: "{profile}"\n\nowners:\n  approvers: {approvers}\n')


def asks(text: str, profile: str = "team") -> dict[str, str]:
    data, _ = documents.split_front_matter(text)
    return {k: level for k, level, _ in authoring.required_docs(data, len(spec_warnings.acceptance_ids(text)), cfg(profile))}


def tables(text: str) -> list[list[str]]:
    """Each Markdown table outside code fences and HTML comments, as its row lines."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    out: list[list[str]] = []
    fenced, current = False, []
    for line in text.splitlines():
        if line.strip().startswith("```"):
            fenced = not fenced
        row = not fenced and line.strip().startswith("|")
        if row:
            current.append(line.strip())
        elif current:
            out.append(current)
            current = []
    return out + ([current] if current else [])


def cells(row: str) -> int:
    return len(re.split(r"(?<!\\)\|", row.strip().strip("|")))


class SchemaTests(unittest.TestCase):
    """The new kinds, the rule conditions, and the `uat` flag are schema, not prose."""

    def test_the_new_kinds_are_doc_kinds_everywhere(self):
        for kind in NEW_KINDS:
            self.assertIn(kind, config.DOC_KINDS)
        spec_kinds = resources.load_json("spec.schema.json")["$defs"]["doc"]["properties"]["kind"]["enum"]
        self.assertEqual(tuple(spec_kinds), config.DOC_KINDS)
        required = resources.load_json("config.schema.json")["properties"]["docs"]["properties"]["required"]["properties"]
        self.assertEqual(set(required), set(config.default_docs_required()))  # a kind aidd has a rule for
        placeholders = resources.load_json("roles.schema.json")
        enum = json.dumps(placeholders)
        for kind in NEW_KINDS:
            self.assertIn(f"{{docs:{kind}}}", enum)
        # A design spec links as `design-spec`, the name of the command and the template.
        self.assertIn("design-spec", config.DOC_KINDS)
        self.assertNotIn("ui", config.DOC_KINDS)

    def test_a_kind_is_warn_or_off_and_aidd_keeps_its_rule(self):
        head = 'aidd_version: "1.0.0"\nprofile: team\n\nowners:\n  approvers: ["@x"]\n\ndocs:\n  required:\n'
        loaded = config.load_text(head + '    migration: "off"\n    test-plan: warn\n')
        self.assertNotIn("migration", loaded.docs_required)
        self.assertEqual(loaded.docs_required["test-plan"], config.default_docs_required()["test-plan"])
        self.assertEqual(config.load_text(head.removesuffix("docs:\n  required:\n")).docs_required, config.default_docs_required())
        # A rule form instead of `warn` or `off`, and a kind aidd has no rule for, fail, never in silence.
        with self.assertRaisesRegex(config.ConfigError, r"docs\.required\.test-plan: must be one of off, warn"):
            config.load_text(head + "    test-plan:\n      routes: [major]\n      any_of: [{uat: true}]\n")
        with self.assertRaisesRegex(config.ConfigError, r"unknown field 'acceptance'"):
            config.load_text(head + "    acceptance: warn\n")

    def test_a_child_cannot_turn_off_a_kind_its_parent_sets_to_warn(self):
        parent = 'aidd_version: "1.0.0"\nprofile: team\ndocs:\n  required:\n    runbook: warn\n'
        child = 'aidd_version: "1.0.0"\nprofile: team\nextends: [{path: p.yaml}]\ndocs:\n  required:\n    runbook: "off"\n    tech-spec: "off"\n'
        loaded = config.load_text(child, read=lambda _: parent)
        self.assertIn("runbook", loaded.docs_required)
        self.assertNotIn("tech-spec", loaded.docs_required)  # the parent left it to the child
        self.assertIn("docs.required.runbook='off' ignored; a parent config sets it to 'warn'", " ".join(loaded.warnings))
        preset = parent.replace("runbook: warn", "runbook:\n      routes: []")
        with self.assertRaisesRegex(config.ConfigError, r"org preset: \$\.docs\.required\.runbook: must be one of off, warn"):
            config.load_text('aidd_version: "1.0.0"\nprofile: team\n', root_preset=preset)

    def test_the_uat_flag_validates(self):
        _, _, errs = spec_file.load_object(spec_text(extra="uat: true\n"), "specs/SPEC-9.md")
        self.assertEqual(errors(errs), [])
        _, _, errs = spec_file.load_object(spec_text(extra='uat: "yes"\n'), "specs/SPEC-9.md")
        self.assertTrue(errors(errs))
        self.assertIn("uat", resources.load_json("spec.schema.json")["properties"])


class MatrixTests(unittest.TestCase):
    """The test plan, the migration plan, and the tracking plan are asked for only when their trigger fires."""

    def test_six_acceptance_items_no_longer_ask_for_a_test_plan(self):
        self.assertNotIn("test-plan", asks(spec_text(route="major", acceptance=9)))
        self.assertNotIn("test-plan", asks(spec_text(acceptance=9)))

    def test_each_trigger_asks_for_a_test_plan(self):
        major = {
            "ten Acceptance items": spec_text(route="major", acceptance=10),
            "a compliance dimension": spec_text(route="major", dims='["compliance"]'),
            "a mobile path": spec_text(route="major", scope='["ios/App/CheckoutView.swift"]'),
            "an Android path": spec_text(route="major", scope='["android/app/src/main/"]'),
            "manual or UAT": spec_text(route="major", extra="uat: true\n"),
        }
        for why, text in major.items():
            self.assertEqual(asks(text).get("test-plan"), "warn", why)
        self.assertEqual(asks(spec_text(route="major"), "audited").get("test-plan"), "warn")
        self.assertNotIn("test-plan", asks(spec_text(route="major"), "team"))
        # On normal each trigger is a suggestion: `aidd validate` stays quiet.
        self.assertEqual(asks(spec_text(extra="uat: true\n")).get("test-plan"), "suggest")
        self.assertEqual(asks(spec_text(acceptance=10)).get("test-plan"), "suggest")

    def test_the_migration_plan_follows_data_and_irreversibility(self):
        self.assertEqual(asks(spec_text(route="major", dims='["data"]')).get("migration"), "warn")
        irreversible = spec_text(route="major").replace("reversible: true", "reversible: false")
        self.assertEqual(asks(irreversible).get("migration"), "warn")
        self.assertEqual(asks(spec_text(dims='["data"]')).get("migration"), "suggest")
        self.assertNotIn("migration", asks(spec_text(route="major", dims='["security"]')))

    def test_a_hypothesis_asks_for_a_tracking_plan(self):
        hyp = 'hypothesis: "checkout conversion moves from 2.1% to 2.4% by 2026-12-01"\n'
        self.assertEqual(asks(spec_text(extra=hyp)).get("analytics"), "warn")
        self.assertEqual(asks(spec_text(route="major", extra=hyp)).get("analytics"), "warn")
        self.assertNotIn("analytics", asks(spec_text()))

    def test_a_solo_founder_minor_change_hears_nothing_new(self):
        self.assertEqual(asks(spec_text(), "solo"), {})

    def test_a_major_change_asks_for_a_tech_spec_and_a_runbook_by_its_reason(self):
        # A protected path alone (CI checks, agent instructions) keeps its security review and specialist approval, and
        # asks for no tech spec and no runbook: nothing new runs to roll out or watch.
        protected_only = asks(spec_text(route="major", ctype="ci", scope='[".github/workflows/ci.yml"]'))
        self.assertNotIn("tech-spec", protected_only)
        self.assertNotIn("runbook", protected_only)
        reasons = {
            "a data dimension": spec_text(route="major", dims='["data"]'),
            "a security dimension": spec_text(route="major", dims='["security"]'),
            "a privacy dimension": spec_text(route="major", dims='["privacy"]'),
            "a financial dimension": spec_text(route="major", dims='["financial"]'),
            "a compliance dimension": spec_text(route="major", dims='["compliance"]'),
            "an availability dimension": spec_text(route="major", dims='["availability"]'),
            "a data type": spec_text(route="major", ctype="data"),
            "an irreversible change": spec_text(route="major").replace("reversible: true", "reversible: false"),
            "a deploy workflow": spec_text(route="major", ctype="ci", scope='[".github/workflows/deploy.yml"]'),
            "a release workflow": spec_text(route="major", ctype="ci", scope='[".github/workflows/release.yaml"]'),
            "infrastructure as code": spec_text(route="major", ctype="infra", scope='["infra/main.tf"]'),
            "a container": spec_text(route="major", ctype="build", scope='["Dockerfile"]'),
        }
        for why, text in reasons.items():
            got = asks(text)
            self.assertEqual((got.get("tech-spec"), got.get("runbook")), ("warn", "warn"), why)
        # A dimension that only rules out minor is no reason on its own.
        self.assertNotIn("runbook", asks(spec_text(route="major", dims='["third_party"]')))
        # The reason reads in the warning, and a normal change is unaffected.
        data, _ = documents.split_front_matter(spec_text(route="major", dims='["availability"]'))
        why = dict((k, w) for k, _, w in authoring.required_docs(data, 2, cfg()))
        self.assertEqual(why["runbook"], "route major, risk availability")
        self.assertNotIn("runbook", asks(spec_text(dims='["availability"]')))


@unittest.skipUnless(shutil.which("git"), "git is required")
class ValidateTests(RepoTemplateCase):
    """`aidd validate` warns for the new triggers and reads the tech spec's Test strategy."""

    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", branch=None)

    def check(self, text, files=None):
        for rel, body in (files or {}).items():
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text(body, encoding="utf-8")
        p = self.root / "specs" / "SPEC-9.md"
        p.parent.mkdir(exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return validation.validate_file(p, "specs/SPEC-9.md")

    def test_validate_warns_and_a_linked_doc_silences_it(self):
        hyp = 'hypothesis: "checkout conversion moves from 2.1% to 2.4% by 2026-12-01"\n'
        found = self.check(spec_text(extra=hyp))
        self.assertEqual(errors(found), [])
        self.assertTrue(any("links no analytics doc" in w and "aidd new analytics" in w for w in warnings(found)), found)
        plan = "specs/SPEC-9/analytics-checkout.md"
        found = self.check(spec_text(("analytics", plan), extra=hyp), {plan: "# Tracking plan\n\nSpec: SPEC-9.\n"})
        self.assertFalse(any("analytics" in w for w in warnings(found)), found)
        found = self.check(spec_text(route="major", ctype="fix", dims='["data"]'))
        self.assertTrue(any("links no migration doc" in w for w in warnings(found)), found)
        self.assertEqual(errors(found), [])

    def test_the_test_strategy_ids_are_the_spec_ones(self):
        body = (
            "# Tech spec\n\nSpec: SPEC-9.\n\n## Test strategy\n\n| Acceptance id | Level | Test file |\n| --- | --- | --- |\n"
            "| A1 | unit | tests/test_cart.py |\n| A2 | e2e | tests/test_cart.py |\n| A7 | e2e | tests/test_cart.py |\n\n## Pre-mortem\n\nA9 is not read here.\n"
        )
        found = self.check(spec_text(("tech-spec", DOC), covers=["A1"]), {DOC: body})
        shown = [w for w in warnings(found) if "Test strategy" in w]
        self.assertTrue(any("A7" in w and "Acceptance" in w for w in shown), shown)
        self.assertTrue(any("A2" in w and "covers" in w for w in shown), shown)
        self.assertFalse(any("A1" in w or "A9" in w for w in shown), shown)
        clean = body.replace("| A7 | e2e | tests/test_cart.py |\n", "")
        found = self.check(spec_text(("tech-spec", DOC)), {DOC: clean})
        self.assertFalse([w for w in warnings(found) if "Test strategy" in w], found)


class TemplateTests(unittest.TestCase):
    """Every template exists, parses, and carries the sections its kind needs."""

    DOC_ASSETS = (
        "tech-spec.md",
        "test-plan.md",
        "design-spec.md",
        "api.md",
        "slo.md",
        "compliance.md",
        "tracking-plan.md",
        "migration-plan.md",
        "acceptance.md",
    )

    def test_every_template_parses(self):
        for p in sorted(ASSETS.glob("*.md")):
            text = read(p)
            if p.name == "DESIGN.md":
                # DESIGN.md's front matter is design.md's token YAML, not aidd's subset: nested mappings, quoted keys, plain
                # scalars such as `1rem`.
                for line in text.split("\n---\n", 1)[0].splitlines()[1:]:
                    self.assertRegex(line, r'^(#.*|\s*"?[A-Za-z0-9_-]+"?:( .+)?|\s*- .+)?$', p.name)
            elif text.startswith("---\n"):
                documents.parse_yaml(text.split("---")[1], p.name)
            for table in tables(text):
                widths = {cells(r) for r in table}
                self.assertEqual(len(widths), 1, f"{p.name}: {table[0]}")
        for name in self.DOC_ASSETS:
            self.assertIn("{{spec}}", asset(name), name)
            self.assertIn("{{spec_link}}", asset(name), name)
        for name in ("contract.md", "change-order.md"):
            self.assertIn("{{proposal}}", asset(name), name)
            self.assertNotIn("{{spec}}", asset(name), name)

    def test_the_tech_spec_holds_the_test_strategy(self):
        tech = asset("tech-spec.md")
        strategy = tech.split("## Test strategy", 1)[1].split("\n## ", 1)[0]
        self.assertRegex(strategy, r"\| Acceptance id \| Level \| Test file \|")
        for word in ("mocked", "performance budget", "axe", "contract test", "Prerequisite", "canary", "smoke"):
            self.assertIn(word.lower(), strategy.lower(), word)
        light = tech.split("## Light variant", 1)[1]
        self.assertIn("Test strategy", light)

    def test_the_test_plan_is_the_audited_or_agency_variant(self):
        plan = asset("test-plan.md")
        for heading in (
            "## Acceptance criteria",
            "## Environments and matrix",
            "## Entry and exit criteria",
            "## Non-functional",
            "## Manual and exploratory",
            "## Reporting",
        ):
            self.assertIn(heading, plan)
        for word in ("device", "browser", "OS", "locale", "charter", "29119-3"):
            self.assertIn(word, plan)
        self.assertIn("Test strategy", plan, "it says the default lives in the tech spec")

    def test_the_design_spec(self):
        ds = asset("design-spec.md")
        for state in ("empty", "loading", "partial", "error", "success", "offline", "permission denied", "first run"):
            self.assertIn(state, ds)
        for target in ("320", "768", "1024", "1440", "iOS", "Android", "compact", "medium", "expanded", "600dp", "840"):
            self.assertIn(target, ds)
        self.assertIn("<screen>-<state>-<target>.png", ds)
        self.assertIn("```mermaid", ds)
        for heading in ("### Web", "### iOS", "### Android", "## Accessibility", "## Content and copy", "## Localization", "## Analytics", "## Test hooks"):
            self.assertIn(heading, ds)
        for word in (
            "Human Interface Guidelines",
            "Material 3",
            "WCAG 2.2",
            "2.5.8",
            "VoiceOver",
            "TalkBack",
            "Dynamic Type",
            "RTL",
            "plural",
            "reduced motion",
            "data-testid",
            "accessibilityIdentifier",
            "testTag",
            "haptic",
            "permission",
        ):
            self.assertIn(word, ds)
        self.assertRegex(ds, r"(?im)^##+ .*light")

    def test_the_prototype_switches_states_and_frames(self):
        ui = asset("prototype.html")
        for state in ("empty", "loading", "partial", "error", "offline", "permission-denied", "success", "first-run"):
            self.assertIn(f'data-state="{state}"', ui)
            self.assertIn(f'data-show="{state}"', ui)
        for frame in ("320", "768", "1024", "1440", "ios", "android"):
            self.assertIn(f'data-frame="{frame}"', ui)
        self.assertEqual(ui.count('<style id="tokens">'), 1)
        tokens = ui.split('<style id="tokens">', 1)[1].split("</style>", 1)[0]
        rest = ui.replace(tokens, "")
        self.assertNotRegex(rest, r"--[a-z0-9-]+\s*:", "every token is defined in the one tokens block")
        fixtures = ui.split('<script type="application/json" id="fixtures">', 1)[1].split("</script>", 1)[0]
        self.assertIsInstance(json.loads(fixtures), dict)
        for tag in re.findall(r"<(?:button|a|input|select|textarea)\b[^>]*>", ui):
            self.assertIn("data-testid=", tag, tag)
        self.assertIn("design artifact", ui.lower())
        self.assertNotRegex(ui, r"<(?:script|link|img)[^>]+(?:src|href)=\"https?://", "the prototype is self-contained")

    def test_the_prototyping_skill(self):
        text = read(PROTOTYPING)
        for word in (
            "<screen>-<state>-<target>.png",
            "toHaveScreenshot",
            "axe",
            "performAccessibilityAudit",
            "Espresso",
            "swift-snapshot-testing",
            "Paparazzi",
            "Roborazzi",
            "Style Dictionary",
            "DTCG",
            "Figma",
            "for example",
            "source of truth",
        ):
            self.assertIn(word, text)
        self.assertNotRegex(text, r"(?:Paparazzi|Roborazzi|swift-snapshot-testing|Style Dictionary) v?\d", "no pinned versions")

    def test_api_slo_and_compliance(self):
        api = asset("api.md")
        for word in (
            "OpenAPI",
            "AsyncAPI 3",
            "RFC 9457",
            "Consumers",
            "Versioning",
            "deprecation",
            "scopes",
            "Idempotency",
            "Pagination",
            "Rate limits",
            "Breaking-change",
            "contract test",
            "tests.commands",
        ):
            self.assertIn(word, api)
        slo = asset("slo.md")
        for word in ("SLI", "Target", "Window", "Error-budget policy", "Alert", "Owner", "Review date"):
            self.assertIn(word, slo)
        comp = asset("compliance.md")
        self.assertIn("| Obligation (law or standard, article) | Control | Evidence (test, file, or gate record) | Owner |", comp)
        # The DPO decides after Spec approval, so the decision lives in the living acceptance record, not here.
        for word in ("DPIA", "Art. 35", "Necessity", "Risks", "Mitigation", "DPO", "acceptance record", "a person"):
            self.assertIn(word, comp)

    def test_the_brief_and_the_prd_lite_epic(self):
        brief = asset("initiative.md").split("## Brief", 1)[1].split("\n## ", 1)[0]
        for item in ("Problem", "Appetite", "Solution sketch", "Rabbit holes", "No-gos", "Success metric"):
            self.assertIn(f"- {item}:", brief)
        epic = asset("epic.md")
        for word in (
            "PRD-lite",
            "Problem and evidence",
            "Users and jobs",
            "Journeys",
            "Appetite",
            "Outcome metrics",
            "Baseline",
            "Target",
            "Non-goals",
            "Rabbit holes",
        ):
            self.assertIn(word, epic)
        self.assertIn("## Brief", asset("initiative.md"))

    def test_the_epic_plans_how_a_large_change_stops_and_recovers(self):
        large = asset("epic.md").split("## Large change", 1)[1].split("\n## ", 1)[0]
        for item in ("Point of no return", "Safe stopping points", "Forward-fix plan", "Target date", "Review date", "Continuity reviewer"):
            self.assertRegex(large, rf"(?m)^- {item}: TODO: ", item)
        self.assertIn("who approves passing it", large)
        self.assertIn("at least two", large)

    def test_the_slo_carries_default_budget_tiers_and_burn_rate_alerts(self):
        slo = asset("slo.md")
        policy = slo.split("## Error-budget policy", 1)[1].split("\n## ", 1)[0]
        for tier in ("| Healthy:", "| Burning:", "| Spent:"):
            self.assertIn(tier, policy)
        self.assertIn("change to fit", policy.lower())
        self.assertIn("go from the SLO owner", policy)
        self.assertIn("Only fixes and reliability work", policy)
        alerts = slo.split("## Alerts", 1)[1].split("\n## ", 1)[0]
        # The Google SRE Workbook, "Alerting on SLOs", table 5-8: rate, long window, short window (1/12 of the long one).
        for row in ("| Page | 14.4× | 1 h | 5 m |", "| Page | 6× | 6 h | 30 m |", "| Ticket | 1× | 3 days | 6 h |"):
            self.assertIn(row, alerts)
        self.assertRegex(alerts, r"https://sre\.google/workbook/alerting-on-slos/\), checked \d{4}-\d{2}-\d{2}")

    def test_tracking_and_migration_plans(self):
        tp = asset("tracking-plan.md")
        for word in ("Object Action", "Trigger", "Properties", "Required", "PII", "Owner", "Platforms", "Question", "Identity", "Naming", "schema validation"):
            self.assertIn(word, tp)
        mp = asset("migration-plan.md")
        for word in (
            "Current",
            "Target",
            "Expand",
            "Migrate",
            "Contract",
            "separate deploy",
            "Backfill",
            "batch",
            "idempotent",
            "row count",
            "lock",
            "timeout",
            "Dual-write",
            "Point of no return",
            "Rollback",
            "Verification queries",
            "Consumers",
            "Retention",
        ):
            self.assertIn(word, mp)

    def test_runbook_postmortem_and_adr(self):
        rollout = asset("runbook.md").split("## Rollout", 1)[1].split("\n## ", 1)[0]
        self.assertIn("### Launch readiness", rollout)
        for word in ("status page", "support", "knowledge base", "release notes", "flag owner", "cleanup date", "go/no-go", "point of no return"):
            self.assertIn(word, rollout.lower() if word.islower() else rollout)
        launch = rollout.split("### Launch readiness", 1)[1].split("\n### ", 1)[0]
        self.assertIn("A line that does not apply says why.", launch)
        for word in ("terms of service", "privacy notice", "DPIA", "dashboards", "alerts", "on-call", "backups", "tested restore"):
            self.assertIn(word, launch)
        checklist = [ln for ln in launch.splitlines() if ln.startswith("- [ ]")]
        self.assertEqual(len(checklist), 8, checklist)
        for line in checklist:
            self.assertIn("owner TODO", line, line)
        point = next(ln for ln in checklist if "Point of no return" in ln)
        self.assertNotIn("and who approves", point, "the owner is named once, in the placeholder")
        pm = asset("postmortem.md")
        for heading in ("## Trigger", "## Root cause", "## Detection", "## Resolution", "## Where we got lucky"):
            self.assertIn(heading, pm)
        self.assertIn("time to detect", pm.lower())
        adr = asset("adr.md")
        self.assertIn("MADR minimal", adr)
        self.assertRegex(adr, r"(?i)short form")

    def test_change_order_and_acceptance_record(self):
        co = asset("change-order.md")
        for word in ("Scope delta", "Price", "Time", "Acceptance ids", "Client decision", "humans only", "Change Request"):
            self.assertIn(word, co)
        acc = asset("acceptance.md")
        for word in ("Acceptance id", "Accepted", "By", "Date", "Evidence", "a person"):
            self.assertIn(word, acc)


@unittest.skipUnless(shutil.which("git"), "git is required")
class NewDocTests(RepoTemplateCase):
    """`aidd new` writes each new kind with its back-link and links it from the Spec."""

    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", spec="02-normal-feature:specs/SPEC-220.md")

    def new(self, *args):
        run = aidd_subprocess("new", *args, cwd=self.root)
        return run.returncode, run.stdout + run.stderr

    def docs(self):
        data, _ = documents.split_front_matter((self.root / "specs" / "SPEC-220.md").read_text(encoding="utf-8"))
        return {d["path"]: d for d in data.get("docs") or []}

    def test_each_new_kind_is_written_and_linked(self):
        want = {
            "api": ("api", "md", True),
            "slo": ("slo", "md", False),
            "compliance": ("compliance", "md", True),
            "analytics": ("analytics", "md", True),
            "migration": ("migration", "md", True),
            "acceptance": ("acceptance", "md", False),
            "design-spec": ("design-spec", "md", True),
        }
        for command, (kind, ext, frozen) in want.items():
            code, out = self.new(command, "Rate limit", "--spec", "SPEC-220")
            self.assertEqual(code, 0, out)
            rel = f"specs/SPEC-220/{command}-rate-limit.{ext}"
            self.assertIn(rel, out)
            body = (self.root / rel).read_text(encoding="utf-8")
            self.assertIn("SPEC-220", body, command)
            self.assertIn("../SPEC-220.md", body, command)  # the back-link to the Spec, beside its folder
            self.assertNotRegex(body, r"\{\{\w+\}\}", command)
            entry = self.docs()[rel]
            self.assertEqual(entry["kind"], kind, command)
            self.assertEqual(entry.get("frozen", True), frozen, command)
        _, _, errs = spec_file.load_object((self.root / "specs" / "SPEC-220.md").read_text(encoding="utf-8"), "specs/SPEC-220.md")
        self.assertEqual(errors(errs), [])

    def test_a_feedback_log_needs_no_spec(self):
        code, out = self.new("feedback", "Pet sitter MVP")
        self.assertEqual(code, 0, out)
        body = (self.root / "docs" / "feedback" / "pet-sitter-mvp.md").read_text(encoding="utf-8")
        self.assertIn("Pet sitter MVP", body)
        self.assertNotIn("\ndocs:", (self.root / "specs" / "SPEC-220.md").read_text(encoding="utf-8"))
        code, out = self.new("api", "limits")
        self.assertNotEqual(code, 0)
        self.assertIn("--spec", out)


class DocsTests(unittest.TestCase):
    """The ceremony by team size, the artifact matrix, and who writes each new kind."""

    def test_the_ceremony_table(self):
        for text in (read(SKILL / "references" / "profiles.md"), read(ROOT / "docs" / "METHOD.md")):
            part = text.split("Ceremony by team size", 1)[1]
            for word in ("Solo", "agency MVP", "spec-short", "Initiative's brief", "prototype", "trigger", "Team", "Audited"):
                self.assertIn(word, part)

    def test_the_artifact_matrix_and_the_guides(self):
        method = read(ROOT / "docs" / "METHOD.md").split("### 4.2 Spec", 1)[1].split("\n### 4.3", 1)[0]
        self.assertRegex(method, r"\| Artifact \| Proposal \| Initiative \| Epic \| Spec normal \| Spec major \| Emergency \| After it lands \|")
        for kind in ("design spec", "api", "slo", "compliance", "analytics", "migration", "change orders", "acceptance", "brief", "contract"):
            self.assertIn(kind, method, kind)
        self.assertIn("not an agency change order", read(ROOT / "docs" / "HOW-TO.md"))
        self.assertIn("aidd new initiative", read(ROOT / "docs" / "HOW-TO.md"))
        self.assertIn('runbook: "off"', read(ROOT / "docs" / "CONFIG.md"))
        self.assertIn("the design spec", read(SKILL / "SKILL.md"))

    def test_who_writes_each_new_kind(self):
        roles = team_registry.roles()["roles"]
        want = {
            "product-manager": ("{docs:analytics}",),
            "delivery-manager": ("{docs:acceptance}",),
            "product-designer": ("{docs:design-spec}",),
            "compliance-analyst": ("{docs:compliance}",),
            "sre": ("{docs:slo}",),
            "architect": ("{docs:api}", "{docs:migration}"),
        }
        for key, entries in want.items():
            for e in entries:
                self.assertIn(e, roles[key]["writes"], key)
        self.assertEqual(json_schema.validate(resources.load_json("roles.json"), "roles.schema.json"), [])


if __name__ == "__main__":
    unittest.main()
