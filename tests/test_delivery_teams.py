"""Several delivery teams in one repository: `delivery_teams` in the config, checked when it loads, and
`aidd status --delivery-team <name>`, which shows one team's work alone. The filter is a view, so it never hides a
team's work by a name that matches nothing: a team that names no known area or harness fails the load."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, git, run_cli

from aidd import config, workitems
from aidd.kernel import resources

HEAD = 'aidd_version: "1.0.0"\nprofile: team\n'


def teams(body: str) -> str:
    return HEAD + "delivery_teams:\n" + body


class ConfigTests(unittest.TestCase):
    """Each team's shape, and the names in it, are checked when the config loads."""

    CASES = (
        # (what, config text, None when it loads, or a piece of the error)
        (
            "areas, harness, and models",
            teams('  payments:\n    people: ["@a"]\n    areas: [payments]\n    harness: opencode\n    models: {reasoning: openai/gpt-5.5}\n'),
            None,
        ),
        ("Epics alone", teams('  web:\n    people: ["@org/web"]\n    epics: [EPIC-1]\n'), None),
        (
            "an area of the config's own",
            HEAD + "risks:\n  areas:\n    search: {paths: ['search/**']}\n" + 'delivery_teams:\n  s:\n    people: ["@a"]\n    areas: [search]\n',
            None,
        ),
        ("no people", teams("  web:\n    epics: [EPIC-1]\n"), "$.delivery_teams.web: missing required field 'people'"),
        ("no one in people", teams("  web:\n    people: []\n    epics: [EPIC-1]\n"), "$.delivery_teams.web.people"),
        ("neither areas nor Epics", teams('  web:\n    people: ["@a"]\n'), "$.delivery_teams.web"),
        ("a name that is no slug", teams('  Web:\n    people: ["@a"]\n    epics: [EPIC-1]\n'), "$.delivery_teams.Web (name)"),
        ("a key the schema has not", teams('  web:\n    people: ["@a"]\n    epics: [EPIC-1]\n    budget: 3\n'), "$.delivery_teams.web: unknown field 'budget'"),
        (
            "a model that is no provider/model",
            teams('  web:\n    people: ["@a"]\n    epics: [EPIC-1]\n    models: {reasoning: gpt}\n'),
            "$.delivery_teams.web.models",
        ),
        (
            "a harness aidd does not know",
            teams('  web:\n    people: ["@a"]\n    epics: [EPIC-1]\n    harness: vscode\n'),
            "delivery_teams.web.harness: 'vscode'",
        ),
        ("an area no rule set defines", teams('  web:\n    people: ["@a"]\n    areas: [frontend]\n'), "delivery_teams.web.areas: 'frontend'"),
        ("a spend cap", HEAD + "agents:\n  max_tokens_per_run: 500000\n", None),
        ("a spend cap of nothing", HEAD + "agents:\n  max_tokens_per_run: 0\n", "$.agents.max_tokens_per_run"),
    )

    def test_each_team_is_checked_as_it_loads(self):
        for what, text, error in self.CASES:
            with self.subTest(what):
                if error is None:
                    config.load_text(text)
                    continue
                with self.assertRaises(config.ConfigError) as caught:
                    config.load_text(text)
                self.assertIn(error, str(caught.exception))

    def test_a_parent_area_counts_once_the_parents_merge(self):
        parent = HEAD + "risks:\n  areas:\n    search: {paths: ['search/**']}\n"
        child = HEAD + 'extends: [{path: base.yaml}]\ndelivery_teams:\n  s:\n    people: ["@a"]\n    areas: [search]\n'
        cfg = config.load_text(child, read=lambda rel: parent if rel == "base.yaml" else None)
        self.assertEqual(config.delivery_team(cfg, "s")["areas"], ["search"])

    def test_the_autopilot_flow_names_the_spend_caps_default(self):
        # One fact, two readers: the schema owns the default, and the lead reads it in the flow.
        cap = resources.load_json("config.schema.json")["properties"]["agents"]["properties"]["max_tokens_per_run"]["default"]
        flow = (ROOT / "plugins" / "aidd-team" / "commands" / "autopilot.md").read_text(encoding="utf-8")
        self.assertTrue("`agents.max_tokens_per_run`" in flow and f"{cap:,} tokens" in flow, cap)


def spec(sid: str, extra: str = "", scope: str = "src/x/**") -> str:
    return f'---\naidd_version: "1.0.0"\ntype: spec\nid: {sid}\ntitle: {sid}\nstatus: draft\n{extra}tasks:\n  - id: T1\n    title: t\n    scope: ["{scope}"]\n---\n'


class MembershipTests(unittest.TestCase):
    """What makes a work item a team's work, with the areas of a scope given."""

    TEAM = {"people": ["@a"], "areas": ["payments"], "epics": ["EPIC-1"]}

    @staticmethod
    def areas(scope: list[str]) -> set[str]:
        return {"payments"} if any("billing" in p for p in scope) else set()

    CASES = (
        ("one of its Epics", {"type": "epic", "id": "EPIC-1"}, True),
        ("another Epic", {"type": "epic", "id": "EPIC-2"}, False),
        ("a Spec under its Epic", {"type": "spec", "id": "SPEC-1", "parent": "EPIC-1"}, True),
        ("a Spec whose scope touches its area", {"type": "spec", "id": "SPEC-2", "tasks": [{"scope": ["src/billing/**"]}]}, True),
        ("a Spec elsewhere", {"type": "spec", "id": "SPEC-3", "parent": "EPIC-2", "tasks": [{"scope": ["web/**"]}]}, False),
        ("a Spec with no Tasks", {"type": "spec", "id": "SPEC-4"}, False),
        ("a Spec whose Tasks do not parse", {"type": "spec", "id": "SPEC-5", "tasks": "src/billing/**"}, False),
        ("a Task whose scope does not parse", {"type": "spec", "id": "SPEC-6", "tasks": [{"scope": "src/billing/**"}]}, False),
        ("an Initiative", {"type": "initiative", "id": "EPIC-1"}, False),
        ("a proposal", {"type": "proposal", "id": "PROP-1"}, False),
    )

    def test_each_item_is_the_teams_work_or_not(self):
        for what, data, expected in self.CASES:
            with self.subTest(what):
                self.assertIs(workitems.in_delivery_team(data, self.TEAM, self.areas), expected)

    def test_a_team_with_epics_alone_takes_no_spec_by_its_scope(self):
        self.assertFalse(workitems.in_delivery_team({"type": "spec", "tasks": [{"scope": ["src/billing/**"]}]}, {"epics": ["EPIC-1"]}, self.areas))


class StatusTests(unittest.TestCase):
    """`aidd status --delivery-team <name>` lists one team's open work, as text and as JSON."""

    CONFIG = teams(
        '  payments:\n    people: ["@a"]\n    areas: [payments]\n'
        '  web:\n    people: ["@b"]\n    epics: [EPIC-1]\n'
        '  both:\n    people: ["@c"]\n    areas: [payments]\n    epics: [EPIC-1]\n'
    )

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        files = {
            ".aidd/config.yaml": self.CONFIG,
            "specs/EPIC-1.md": '---\naidd_version: "1.0.0"\ntype: epic\nid: EPIC-1\ntitle: e\ngoal: g\n---\n',
            "specs/SPEC-1.md": spec("SPEC-1", scope="src/billing/**"),
            "specs/SPEC-2.md": spec("SPEC-2", "parent: EPIC-1\n", "web/**"),
            "specs/SPEC-3.md": spec("SPEC-3", scope="docs/**"),
        }
        for rel, text in files.items():
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text(text, encoding="utf-8")
        git(self.root, "init", "-q", "-b", "main")

    def cli(self, *argv: str) -> tuple[int, str]:
        here = os.getcwd()
        os.chdir(self.root)
        try:
            return run_cli(*argv)
        finally:
            os.chdir(here)

    CASES = (
        ("payments", ["SPEC-1"]),
        ("web", ["EPIC-1", "SPEC-2"]),
        ("both", ["EPIC-1", "SPEC-1", "SPEC-2"]),
    )

    def test_each_team_sees_its_own_work(self):
        for name, ids in self.CASES:
            with self.subTest(name):
                code, out = self.cli("status", "--delivery-team", name, "--json")
                self.assertEqual(code, 0, out)
                self.assertEqual(sorted(i["id"] for i in json.loads(out)["items"]), ids)
                code, out = self.cli("status", "--delivery-team", name)
                self.assertEqual(code, 0, out)
                self.assertEqual(sorted(line.split()[0] for line in out.splitlines() if not line.startswith(" ")), ids)

    def test_without_the_flag_every_item_shows(self):
        code, out = self.cli("status", "--json")
        self.assertEqual(sorted(i["id"] for i in json.loads(out)["items"]), ["EPIC-1", "SPEC-1", "SPEC-2", "SPEC-3"])

    def test_an_epic_keeps_its_whole_progress(self):
        code, out = self.cli("status", "--delivery-team", "web", "--json")
        epic = next(i for i in json.loads(out)["items"] if i["id"] == "EPIC-1")
        self.assertEqual(epic["progress"], {"finished": 0, "of": 1})

    def test_another_teams_spec_still_blocks_one_of_this_teams(self):
        """The filter is a view: SPEC-1 (payments) blocks SPEC-2 (web), so web's SPEC-2 still reads as blocked."""
        path = self.root / "specs" / "SPEC-2.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace("parent: EPIC-1\n", "parent: EPIC-1\nrelations: [{type: blocked_by, id: SPEC-1}]\n"), encoding="utf-8"
        )
        code, out = self.cli("status", "--delivery-team", "web", "--json")
        item = next(i for i in json.loads(out)["items"] if i["id"] == "SPEC-2")
        self.assertEqual((item["waiting_on"], item["next"]["code"]), (["SPEC-1"], "spec.blocked_by"))

    def test_a_team_the_config_does_not_name_is_an_error_that_names_the_teams(self):
        code, out = self.cli("status", "--delivery-team", "mobile")
        self.assertNotEqual(code, 0)
        self.assertIn("both, payments, web", out)


if __name__ == "__main__":
    unittest.main()
