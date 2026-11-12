"""The artifact set. Testing lives in the Spec's Acceptance and its test plan; a migration plan and a tracking plan are
asked for only when their trigger fires; a design spec, API, SLO, compliance,
and acceptance templates, the Intent, and the contract and change-order family; and a ceremony table that
keeps a solo founder near zero.
"""

import json
import re
import shutil
import unittest

from helpers import PROTOTYPE_EXAMPLE, PROTOTYPE_TOOL, PROTOTYPE_VIEWER, ROOT, RepoTemplateCase, aidd_here, make_repo

from aidd.workitems import authoring
from aidd import config
from aidd.kernel import documents, json_schema, resources
from aidd.knowledge import team_registry

SKILL = ROOT / ".agents" / "skills" / "aidd"
ASSETS = SKILL / "assets"
PROTOTYPING = ROOT / "plugins" / "aidd-team" / "skills" / "prototyping" / "SKILL.md"
NEW_TYPES = ("tracking-plan", "migration-plan", "acceptance")


def read(path) -> str:
    return path.read_text(encoding="utf-8")


def asset(name: str) -> str:
    return read(ASSETS / name)


def cfg(profile: str = "team"):
    approvers = '["@x", "@y"]' if profile == "audited" else '["@x"]'
    return config.load_text(f'aidd_version: "1.0.0"\nprofile: "{profile}"\n\nowners:\n  approvers: {approvers}\n')


def asks(text: str, profile: str = "team") -> dict[str, str]:
    data, _ = documents.split_front_matter(text)
    return {k: level for k, level, *_ in authoring.required_docs(data, cfg(profile))}


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
    """The new types, the rule conditions, and the `manual_acceptance` flag are schema, not prose."""

    def test_the_new_types_are_doc_types_everywhere(self):
        for doc_type in NEW_TYPES:
            self.assertIn(doc_type, config.DOC_TYPES)
        spec_types = resources.load_json("spec.schema.json")["$defs"]["doc"]["properties"]["type"]["enum"]
        self.assertEqual(tuple(spec_types), config.DOC_TYPES)
        required = resources.load_json("config.schema.json")["properties"]["docs"]["properties"]["disabled"]["properties"]
        self.assertEqual(set(required), set(config.default_docs_required()))  # a type aidd has a rule for
        placeholders = resources.load_json("roles.schema.json")
        enum = json.dumps(placeholders)
        for doc_type in NEW_TYPES:
            self.assertIn(f"{{docs:{doc_type}}}", enum)
        # A design spec links as `design-spec`, the name of the command and the template.
        self.assertIn("design-spec", config.DOC_TYPES)
        self.assertNotIn("ui", config.DOC_TYPES)

    def test_a_disabled_type_has_a_reason_and_aidd_keeps_its_rule_for_the_rest(self):
        head = 'aidd_version: "1.0.0"\nprofile: team\n\nowners:\n  approvers: ["@x"]\n\ndocs:\n  disabled:\n'
        loaded = config.load_text(head + "    migration-plan: no database here\n")
        self.assertNotIn("migration-plan", loaded.docs_required)
        self.assertEqual(loaded.docs_required["test-plan"], config.default_docs_required()["test-plan"])
        self.assertEqual(config.load_text(head.removesuffix("docs:\n  disabled:\n")).docs_required, config.default_docs_required())
        # A type is never switched off with no reason, and a type aidd has no rule for fails, never in silence.
        with self.assertRaisesRegex(config.ConfigError, r"docs\.disabled\.test-plan"):
            config.load_text(head + '    test-plan: ""\n')
        with self.assertRaisesRegex(config.ConfigError, r"unknown field 'acceptance'"):
            config.load_text(head + "    acceptance: no acceptance docs\n")

    def test_a_child_adds_types_to_its_parents_and_only_a_lock_freezes_them(self):
        parent = 'aidd_version: "1.0.0"\nprofile: team\ndocs:\n  disabled:\n    runbook: a library\n'
        child = 'aidd_version: "1.0.0"\nprofile: team\nextends: [{path: p.yaml}]\ndocs:\n  disabled:\n    runbook: a different reason\n    tech-spec: no design docs\n'
        loaded = config.load_text(child, read=lambda _: parent)
        self.assertEqual(loaded.get("docs", "disabled"), {"runbook": "a different reason", "tech-spec": "no design docs"})
        self.assertNotIn("runbook", loaded.docs_required)
        self.assertEqual(loaded.warnings, [])  # no hidden lock: the parent set no lock
        other = parent.replace("docs:", "docs:\n  dir: handbook").replace("profile: team", "profile: team\nlocks: [docs.disabled]")
        frozen = config.load_text(child, read=lambda _: other)
        self.assertEqual(frozen.get("docs", "disabled"), {"runbook": "a library"})
        self.assertEqual(frozen.docs_dir, "handbook")
        self.assertIn("docs.disabled is locked by a parent config", " ".join(frozen.warnings))
        preset = parent.replace("runbook: a library", "runbook:\n      routes: []")
        with self.assertRaisesRegex(config.ConfigError, r"org preset: line 5: \$\.docs\.disabled\.runbook"):
            config.load_text('aidd_version: "1.0.0"\nprofile: team\n', root_preset=preset)


class TemplateTests(unittest.TestCase):
    """Every template exists, parses, and carries the sections its type needs."""

    DOC_ASSETS = (
        "tech-spec.md",
        "test-plan.md",
        "design-spec.md",
        "api.md",
        "slo.md",
        "compliance-record.md",
        "tracking-plan.md",
        "migration-plan.md",
        "acceptance.md",
    )

    def test_every_template_parses(self):
        for p in sorted(ASSETS.glob("*.md")):
            text = read(p)
            if text.startswith("---\n"):
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

    def test_the_tech_spec_links_the_test_plan_and_holds_no_test_strategy(self):
        tech = asset("tech-spec.md")
        for gone in ("## Test strategy", "## Open questions", "## Light variant", "Retention", "Non-goals", "non-goals and"):
            self.assertNotIn(gone, tech, gone)
        testing = tech.split("### Testing", 1)[1].split("\n## ", 1)[0]
        self.assertIn("aidd new test-plan", testing)
        self.assertIn("test plan", tech.split("## Cross-cutting concerns", 1)[0].lower())  # the header names it among the fact owners

    def test_the_test_plan_has_the_29119_3_information_items_at_two_templates(self):
        plan = asset("test-plan.md")
        for heading in (
            "## Scope",
            "## Risks",
            "## Test approach",
            "## Non-functional checks",
            "## Environments and data",
            "## Entry, exit, and suspension",
            "## Manual and exploratory",
            "## Reporting",
            "## Audit additions",
        ):
            self.assertIn(heading, plan)
        self.assertNotIn("## Acceptance criteria", plan)
        for word in ("device", "browser", "OS", "locale", "charter", "29119-3"):
            self.assertIn(word, plan)
        approach = plan.split("## Test approach", 1)[1].split("\n## ", 1)[0]
        self.assertIn("| Acceptance id | Level | Real or mocked | Technique |", approach)
        self.assertNotIn("Behavior", plan)  # the Spec's Acceptance owns the text
        living = asset("test-plan-living.md")
        for heading in (
            "## Conformance",
            "## Scope and test basis",
            "## Test strategy",
            "## Environments and matrix",
            "## Risk register and coverage",
            "## Test catalog",
            "## Traceability and evidence",
        ):
            self.assertIn(heading, living)
        self.assertIn("aidd new srs product", living)
        self.assertNotRegex(living, r"(?m)^\|.*\| (A\d|covered) \|", "the trace is generated, never a typed matrix")

    def test_the_design_spec(self):
        ds = asset("design-spec.md")
        for state in ("empty", "loading", "partial", "error", "success", "offline", "permission denied", "first run"):
            self.assertIn(state, ds)
        for target in ("320", "768", "1024", "1440", "iOS", "Android", "compact", "medium", "expanded", "600dp", "840"):
            self.assertIn(target, ds)
        self.assertIn("<screen>-<state>-<frame>.png", ds)
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
        self.assertRegex(ds, r"(?s)<!-- The light variant.*?keeps these sections: Context of use, Flows,")
        self.assertNotRegex(ds, r"(?im)^##+ .*light", "the light variant is a note for `aidd new`, not a section")
        context = ds.split("## Context of use", 1)[1].split("\n## ", 1)[0]
        for word in ("ISO 9241-210", "Users", "Goals", "Tasks", "Environment", "Intent", "Users, and never copy"):
            self.assertIn(word, context)
        for name in ("Claude Design", "Figma"):
            self.assertNotIn(name, ds)

    def test_the_prototype_switches_states_and_frames(self):
        ui = PROTOTYPE_VIEWER.read_text(encoding="utf-8") + PROTOTYPE_EXAMPLE.read_text(encoding="utf-8")
        for state in ("empty", "loading", "partial", "error", "offline", "permission-denied", "success", "first-run"):
            self.assertIn(f'data-state="{state}"', ui)
            self.assertIn(f'data-show="{state}"', ui)
        for frame in ("320", "768", "1024", "1440", "ios", "android"):
            self.assertIn(f'data-frame="{frame}"', ui)
        self.assertEqual(ui.count('<style id="tokens">'), 1)
        tokens = ui.split('<style id="tokens">', 1)[1].split("</style>", 1)[0]
        viewer = ui.split('<style id="viewer">', 1)[1].split("</style>", 1)[0]
        self.assertEqual({v for v in re.findall(r"(--[a-z0-9-]+)\s*:", viewer) if not v.startswith("--pv-")}, set(), "the viewer's own palette")
        rest = ui.replace(tokens, "").replace(viewer, "")
        self.assertNotRegex(rest, r"--[a-z0-9-]+\s*:", "every token is defined in the one tokens block")
        fixtures = ui.split('<script type="application/json" id="fixtures">', 1)[1].split("</script>", 1)[0]
        self.assertIsInstance(json.loads(fixtures), dict)
        for tag in re.findall(r"<(?:button|a|input|select|textarea)\b[^>]*>", ui):
            self.assertIn("data-testid=", tag, tag)
        # The starting design calls itself a design artifact; the showcase is an example no Spec freezes.
        self.assertIn("design artifact", (PROTOTYPE_TOOL / "design.html").read_text(encoding="utf-8").lower())
        self.assertNotRegex(ui, r"<(?:script|link|img)[^>]+(?:src|href)=\"https?://", "the prototype is self-contained")

    def test_the_prototyping_skill(self):
        text = read(PROTOTYPING)
        for word in (
            "<screen>-<state>-<frame>.png",
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
        for word in ("SLI", "Was", "Becomes", "Window", "Alert", "Review date", "Why", "Frozen at Spec approval", "service card"):
            self.assertIn(word, slo)
        # The delta holds no current objectives: the budget tiers, the alert table, the rationale, and the clarifications are the card's.
        for heading in ("## Alerts", "## Error-budget policy", "## Rationale", "## Clarifications and caveats"):
            self.assertNotIn(heading, slo)
        self.assertNotIn("| Healthy:", slo)
        card = asset("service-card.md")
        self.assertIn("| SLI | Target | Window | Error-budget policy | Alert | Owner | Review date |", card)
        for heading in ("## Rationale", "## Clarifications and caveats", "## Changes"):
            self.assertIn(heading, card)
        comp = asset("compliance-record.md")
        self.assertIn("| Control id | Obligation (law or standard, article) | Control | Evidence (test, file, or `aidd test` evidence) | Owner |", comp)
        # The DPO decides after Spec approval, so the decision lives in the living acceptance record, not here.
        for word in ("DPIA", "Art. 35", "Necessity", "Risks", "Mitigation", "DPO", "acceptance record", "a person"):
            self.assertIn(word, comp)

    def test_the_intent_quotes_the_request_and_holds_the_plan(self):
        intent = asset("intent.md")
        for heading in (
            "## Problem",
            "## Outcome",
            "## Who and what it touches",
            "## Constraints",
            "## Request coverage",
            "### First slice",
            "## Open questions",
            "## Out of scope",
            "## Learn",
        ):
            self.assertIn(heading, intent)
        self.assertRegex(intent, r"(?m)^- Acceptance:\n  - A1: TODO: .*2 to 5 lines")
        self.assertIn("Quote the request", intent)
        front = documents.parse_yaml(intent.split("---")[1], "intent.md")
        self.assertEqual(front["type"], "intent")
        self.assertEqual(set(front["phases"][0]), {"id", "name", "slices"})
        self.assertEqual(set(front["phases"][0]["slices"][0]), {"id", "title"})
        self.assertNotIn("slices", front, "an Intent lists its slices in `phases` only")
        for word in ("appetite", "baseline", "(assumed)"):
            self.assertIn(word, intent.lower())

    def test_the_intent_plans_how_a_large_change_stops_and_recovers(self):
        large = asset("intent.md").split("### Large change", 1)[1].split("\n## ", 1)[0]
        for item in ("Point of no return", "Safe stopping points", "Forward-fix plan", "Target date", "Review date", "Continuity reviewer"):
            self.assertRegex(large, rf"(?m)^- {item}: TODO: ", item)
        self.assertIn("who approves passing it", large)
        self.assertIn("at least two", large)

    def test_the_service_card_carries_default_budget_tiers_and_burn_rate_alerts(self):
        slo = asset("service-card.md")
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
        runbook = asset("runbook.md")
        for heading in ("## Purpose", "## When to use", "## Prerequisites", "## Steps", "## Verification", "## Rollback", "## Escalation", "## Restore"):
            self.assertIn(heading, runbook)
        for moved in ("\n## Rollout\n", "### Launch readiness", "\n## On-call\n", "\n## Handover\n"):
            self.assertNotIn(moved, runbook, f"{moved} has its own home: the Spec's Rollout, the service card, the acceptance record")
        rollout = (SKILL / "references" / "spec-release.md").read_text(encoding="utf-8").split("## Rollout (`## Rollout`)", 1)[1].split("\n## ", 1)[0]
        self.assertIn("### Launch readiness", rollout)
        for word in ("status page", "support", "kb article", "release notes", "go/no-go", "point of no return", "go threshold", "no-go threshold"):
            self.assertIn(word, rollout.lower())
        for word in ("terms", "privacy notice", "DPIA", "dashboards", "alerts", "on-call", "tested restore", "cleanup date"):
            self.assertIn(word, rollout)
        self.assertIn("one that does not apply says why", rollout)
        checklist = [ln for ln in rollout.splitlines() if ln.startswith("- [ ]")]
        self.assertEqual(len(checklist), 8, checklist)
        for line in checklist:
            self.assertIn("owner TODO", line, line)
        pm = asset("postmortem.md")
        for heading in ("## Trigger", "## Root cause", "## Detection", "## Resolution", "## Where we got lucky"):
            self.assertIn(heading, pm)
        self.assertIn("time to detect", pm.lower())
        adr = asset("adr.md")
        self.assertIn("MADR minimal", adr)
        self.assertRegex(adr, r"(?i)short form")

    def test_change_order_and_acceptance_record(self):
        co = asset("change-order.md")
        for word in ("Scope delta", "Price", "Time", "Acceptance ids", "Client decision", "humans only"):
            self.assertIn(word, co)
        acc = asset("acceptance.md")
        for word in ("Acceptance id", "Accepted", "By", "Date", "Evidence", "a person"):
            self.assertIn(word, acc)


@unittest.skipUnless(shutil.which("git"), "git is required")
class NewDocTests(RepoTemplateCase):
    """`aidd new` writes each new type with its back-link and links it from the Spec."""

    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", spec="02-normal-feature:specs/SPEC-220.md")

    def new(self, *args):
        run = aidd_here("new", *args, cwd=self.root)
        return run.returncode, run.stdout + run.stderr

    def docs(self):
        data, _ = documents.split_front_matter((self.root / "specs" / "SPEC-220.md").read_text(encoding="utf-8"))
        return {d["path"]: d for d in data.get("docs") or []}

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
    """The ceremony by team size, the artifact matrix, and who writes each new type."""

    def test_the_ceremony_table(self):
        for text in (read(SKILL / "references" / "profiles.md"),):
            part = text.split("Ceremony by team size", 1)[1]
            for word in ("Solo", "agency MVP", "spec-short", "the Intent", "prototype", "trigger", "Team"):
                self.assertIn(word, part)

    def test_the_config_reference_and_the_skill(self):
        self.assertIn("`docs.disabled`", read(ROOT / "docs" / "CONFIG.md"))
        self.assertIn("design-spec", read(SKILL / "references" / "spec-docs.md"))

    def test_who_writes_each_new_type(self):
        roles = team_registry.roles()["roles"]
        want = {
            "product-manager": ("{docs:tracking-plan}",),
            "delivery-manager": ("{docs:acceptance}",),
            "product-designer": ("{docs:design-spec}",),
            "compliance-analyst": ("{docs:compliance-record}",),
            "sre": ("{docs:slo}",),
            "architect": ("{docs:api}", "{docs:migration-plan}"),
        }
        for key, entries in want.items():
            for e in entries:
                self.assertIn(e, roles[key]["writes"], key)
        self.assertEqual(json_schema.validate(resources.load_json("roles.json"), "roles.schema.json"), [])


if __name__ == "__main__":
    unittest.main()
