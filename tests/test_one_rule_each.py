"""One rule each for three questions aidd used to answer in several places, where the answers disagreed:

- Is this identity an agent or a bot, and so never a person who decides? `config.identities.is_agent`, which the gate,
  `aidd validate`, the waivers, the work items, and the explorations all read.
- Is the aidd-team installed here? `config.harness_settings.team_installed`, which the guard, `aidd doctor`, and the
  next steps all read.
- Which day does a value name? `kernel.timestamps.parse_date`, which the waivers, upkeep, and the rollups all read.

Each class pins the one answer, through the callers that used to disagree, and checks that no second definition is
left to drift.
"""

from __future__ import annotations

import ast
import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT, decide, example, rules

from aidd import config
from aidd.workitems import triage
from aidd.config import harness_settings, identities, project
from aidd.kernel import timestamps

SRC = ROOT / "src" / "aidd"


def definitions(name: str) -> list[str]:
    """Every module under src/aidd that defines `name` at its top level, by path."""
    out = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name for n in tree.body):
            out.append(path.relative_to(SRC).as_posix())
    return out


# Agents and bots, each the way a config, a Spec, or a platform writes one.
AGENTS = (
    "agent:claude-code/claude-opus-5-5",  # an agent identity whose name runs on past a known agent's name
    "agent:my-bot",
    "Agent:Developer",  # identities are case-insensitive
    "acme:agent:developer",  # tenant-qualified
    "@claude",  # a login that is a known agent's name
    "claude",
    "acme:@claude",
    "email:noreply@anthropic.com",  # an agent's commit address
    "email:helper[bot]@users.noreply.github.com",
    "renovate[bot]",
    "@web-flow",
    "copilot-pull-request-reviewer",  # a login the baseline names as an agent
    "@Release-Bot",  # configured in identities.bots, written another way
    "acme:@release-bot",
)
PEOPLE = ("@alice", "alice", "acme:@alice", "email:alice@example.com", "@claude-martin", "@release-botanist")
BOTS = {"release-bot"}


class OneAgentRuleTests(unittest.TestCase):
    def test_every_agent_and_bot_is_one(self):
        for who in AGENTS:
            with self.subTest(who):
                self.assertTrue(identities.is_agent(who, BOTS))

    def test_a_person_is_not(self):
        for who in PEOPLE:
            with self.subTest(who):
                self.assertFalse(identities.is_agent(who, BOTS))
        self.assertFalse(identities.is_agent(None, BOTS))
        self.assertFalse(identities.is_agent("", BOTS))

    def test_a_lookalike_of_an_agent_is_one(self):
        """Unicode lookalikes read as what they look like when aidd asks whether an identity is an agent: NFKC folds a
        fullwidth letter, format characters such as a zero-width space are dropped, and a letter outside ASCII that is
        left (a Cyrillic `а`) is read as an agent. Only this detection folds; equality never does."""
        lookalikes = {
            "ａgent:x": "agent:x",  # fullwidth a
            "agent​:x": "agent:x",  # zero-width space
            "@cl­aude": "claude",  # soft hyphen, a format character
            "аgent:x": None,  # Cyrillic a: no fold, so the non-ASCII letter decides
            "clаude": None,
        }
        for who, folded in lookalikes.items():
            with self.subTest(who=who.encode("unicode_escape").decode()):
                self.assertTrue(identities.is_agent(who, BOTS))
                if folded:
                    self.assertEqual(identities._detection_key(who), folded)
                    # The equality key never folds: a lookalike never equals the identity it imitates.
                    self.assertNotEqual(identities.normalize_identity(who), folded)
        # A person's ASCII login is unchanged by the folding.
        self.assertEqual(identities.normalize_identity(" @Alice "), "alice")
        self.assertFalse(identities.is_agent("@ａlice", BOTS))  # fullwidth, folded to plain ASCII `alice`

    def test_the_gate_refuses_an_agent_as_the_incident_commander(self):
        # The emergency rule read `is_agent` without the `agent:` kind: an agent identity could command the incident.
        for who in ("agent:claude-code/claude-opus-5-5", "acme:agent:developer", "email:noreply@anthropic.com"):
            with self.subTest(who):
                ctx = example("05-emergency-under-freeze")
                ctx["base_config"] = ctx["base_config"].replace("profile: org", "profile: solo")
                ctx["change"]["body"] = ctx["change"]["body"].replace('commander: "@oncall-lead"', f'commander: "{who}"')
                d = decide(ctx)
                self.assertIn("emergency", rules(d, "fail"))
                self.assertIn("emergency.commander_is_agent", {f.code for f in d.findings})

    def test_a_waiver_needs_a_person(self):
        # The waiver check knew `agent:` but not a known agent's login or address.
        head = 'aidd_version: "1.0.0"\nprofile: team\nowners: {approvers: ["@org/leads"]}\n'
        rule = 'project:\n  rules:\n    - id: r1\n      level: must\n      statement: s\n      why: w\n      owner: "@a"\n'
        for who in ("@claude", "email:noreply@anthropic.com", "copilot-swe-agent"):
            waiver = f'  waivers:\n    - rule: r1\n      reason: r\n      approved_by: "{who}"\n      until: "2027-01-01"\n'
            with self.subTest(who):
                errors, _ = project.project_findings(config.load_text(head + rule + waiver), dt.date(2026, 9, 30))
                self.assertTrue(any("a person approves a waiver" in e for e in errors), errors)

    def test_work_items_need_a_person_to_own_and_triage_them(self):
        # The work-item check read `agent:` case-sensitively, with no tenant and no known agent names.
        for who in ("Agent:Developer", "acme:agent:developer", "@claude", "acme:@release-bot"):
            with self.subTest(who):
                self.assertTrue(triage.owner_errors({"kind": "spec", "owner": who}, BOTS))
                spec = {"kind": "spec", "suggested_by": "agent:developer", "status": "ready", "triage": {"decision": "accepted", "by": who}}
                self.assertTrue(any("is an agent account" in e for e in triage.triage_errors(spec, BOTS)))

    def test_one_definition(self):
        self.assertEqual(definitions("is_agent"), ["config/identities.py"])


class OneReviewCadenceTests(unittest.TestCase):
    def test_one_table_of_review_days(self):
        """The registry and the library review a standard on one cadence, defined once (knowledge.team_registry)."""
        from aidd.knowledge import upkeep
        from aidd.knowledge import standards, team_registry

        defined = []
        for path in sorted(SRC.rglob("*.py")):
            for node in ast.parse(path.read_text(encoding="utf-8")).body:
                if (
                    isinstance(node, ast.Assign)
                    and any(getattr(t, "id", None) == "REVIEW_EVERY_DAYS" for t in node.targets)
                    and isinstance(node.value, ast.Dict)
                ):
                    defined.append(path.relative_to(SRC).as_posix())
        self.assertEqual(defined, ["knowledge/team_registry.py"])
        self.assertIs(upkeep.REVIEW_EVERY_DAYS, team_registry.REVIEW_EVERY_DAYS)
        self.assertIs(standards.LIBRARY_REVIEW_EVERY_DAYS, team_registry.REVIEW_EVERY_DAYS)


class OneTeamRuleTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "repo"
        self.user = Path(tmp.name) / "user"
        self.root.mkdir()
        self.user.mkdir()
        env = mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.user)})
        env.start()
        self.addCleanup(env.stop)

    def settings(self, folder: Path, name: str, on: bool) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(json.dumps({"enabledPlugins": {f"aidd-team@{harness_settings.MARKETPLACE}": on}}), encoding="utf-8")

    def test_nothing_is_not_a_team(self):
        self.assertFalse(harness_settings.team_installed(self.root))

    def test_the_agents_md_section_init_writes(self):
        # `aidd init --team` writes it for every harness; the guard did not read it.
        (self.root / "AGENTS.md").write_text(f"# Agents\n\n{harness_settings.TEAM_MARK}\n", encoding="utf-8")
        self.assertTrue(harness_settings.team_installed(self.root))

    def test_the_claude_code_role_files(self):
        # `aidd init --team` writes them for Claude Code; the next steps did not read them.
        (self.root / ".claude" / "agents").mkdir(parents=True)
        (self.root / ".claude" / "agents" / f"{harness_settings.TEAM_PREFIX}developer.md").write_text("---\nname: x\n---\n", encoding="utf-8")
        self.assertTrue(harness_settings.team_installed(self.root))

    def test_the_plugin_as_claude_code_enables_it(self):
        self.settings(self.root / ".claude", "settings.json", True)
        self.assertTrue(harness_settings.team_installed(self.root))
        # The local settings decide over the project's, as Claude Code reads them; the next steps took any `true`.
        self.settings(self.root / ".claude", "settings.local.json", False)
        self.assertFalse(harness_settings.team_installed(self.root))

    def test_the_plugin_enabled_for_this_user(self):
        # Claude Code loads the user's settings too; the next steps read only the project's.
        self.settings(self.user, "settings.json", True)
        self.assertTrue(harness_settings.team_installed(self.root))

    def test_one_definition(self):
        self.assertEqual(definitions("team_installed"), ["config/harness_settings.py"])


class OneDateRuleTests(unittest.TestCase):
    def test_a_date_or_the_day_of_a_timestamp(self):
        day = dt.date(2026, 10, 12)
        for value in ("2026-10-12", "2026-10-12T09:30:00Z", "2026-10-12 09:30:00+00:00", day, dt.datetime(2026, 10, 12, 9, 30)):
            with self.subTest(value):
                self.assertEqual(timestamps.parse_date(value), day)
        for value in (None, "", "next week", "2026-13-01"):
            with self.subTest(value):
                self.assertIsNone(timestamps.parse_date(value))

    def test_a_waiver_until_a_timestamp_holds_until_that_day(self):
        # The waivers did not cut a timestamp to its date: the waiver read as no waiver at all.
        waiver = {"rule": "r1", "until": "2027-01-01T00:00:00Z", "approved_by": "@a", "reason": "r"}
        held = project._waiver("r1", [waiver], dt.date(2026, 9, 30))
        self.assertIsNotNone(held)

    def test_one_definition(self):
        self.assertEqual(definitions("_date"), [])
        self.assertEqual(definitions("parse_date"), ["kernel/timestamps.py"])


if __name__ == "__main__":
    unittest.main()
