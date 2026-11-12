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
from aidd.kernel import json_schema, resources

HEAD = 'aidd_version: "1.0.0"\nprofile: team\n'


def teams(body: str) -> str:
    return HEAD + "delivery_teams:\n" + body


class ConfigTests(unittest.TestCase):
    """Each team's shape, and the names in it, are checked when the config loads."""

    CASES = (
        # (what, config text, None when it loads, or a piece of the error)
        (
            "areas, harness, and models",
            teams('  payments:\n    approvers: ["@a"]\n    areas: [payments]\n    harness: opencode\n    models: {reasoning: openai/gpt-5.5}\n'),
            None,
        ),
        ("approvers alone", teams('  web:\n    approvers: ["@org/web"]\n'), None),
        (
            "an area of the config's own",
            HEAD + "risks:\n  areas:\n    search: {paths: ['search/**']}\n" + 'delivery_teams:\n  s:\n    approvers: ["@a"]\n    areas: [search]\n',
            None,
        ),
        ("no approvers", teams("  web:\n    areas: [payments]\n"), "$.delivery_teams.web: missing required field 'approvers'"),
        ("a key the schema does not know", teams('  web:\n    approvers: ["@a"]\n    epics: [EPIC-1]\n'), "$.delivery_teams.web: unknown field 'epics'"),
        ("no one in approvers", teams("  web:\n    approvers: []\n"), "$.delivery_teams.web.approvers"),
        ("a dropped intents list", teams('  web:\n    approvers: ["@a"]\n    intents: [INTENT-1]\n'), "$.delivery_teams.web: unknown field 'intents'"),
        ("a name that is no slug", teams('  Web:\n    approvers: ["@a"]\n'), "$.delivery_teams.Web (name)"),
        (
            "a key the schema has not",
            teams('  web:\n    approvers: ["@a"]\n    budget: 3\n'),
            "$.delivery_teams.web: unknown field 'budget'",
        ),
        (
            "a model that is no provider/model",
            teams('  web:\n    approvers: ["@a"]\n    models: {reasoning: gpt}\n'),
            "$.delivery_teams.web.models",
        ),
        (
            "an effort keyed as agents.effort is",
            teams('  web:\n    approvers: ["@a"]\n    effort: {reasoning: high, verifier: max}\n'),
            None,
        ),
        (
            "an effort that is no level",
            teams('  web:\n    approvers: ["@a"]\n    effort: {reasoning: huge}\n'),
            "$.delivery_teams.web.effort",
        ),
        (
            "the old name of approvers",
            teams('  web:\n    people: ["@a"]\n'),
            "$.delivery_teams.web: unknown field 'people'",
        ),
        (
            "a harness aidd does not know",
            teams('  web:\n    approvers: ["@a"]\n    harness: vscode\n'),
            "delivery_teams.web.harness: 'vscode'",
        ),
        ("an area no rule set defines", teams('  web:\n    approvers: ["@a"]\n    areas: [frontend]\n'), "delivery_teams.web.areas: 'frontend'"),
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
        child = HEAD + 'extends: [{path: base.yaml}]\ndelivery_teams:\n  s:\n    approvers: ["@a"]\n    areas: [search]\n'
        cfg = config.load_text(child, read=lambda rel: parent if rel == "base.yaml" else None)
        self.assertEqual(config.delivery_team(cfg, "s")["areas"], ["search"])

    def test_the_autopilot_flow_names_the_spend_caps_default(self):
        # One fact, two readers: the schema owns the default, and the lead reads it in the flow.
        cap = resources.load_json("config.schema.json")["properties"]["agents"]["properties"]["max_tokens_per_run"]["default"]
        flow = (ROOT / "plugins" / "aidd-team" / "commands" / "autopilot.md").read_text(encoding="utf-8")
        self.assertTrue("`agents.max_tokens_per_run`" in flow and f"{cap:,} tokens" in flow, cap)


def spec(sid: str, extra: str = "", scope: str = "src/x/**") -> str:
    return f'---\ntype: spec\nid: {sid}\ntitle: {sid}\nstatus: draft\n{extra}tasks:\n  - id: T1\n    title: t\n    scope: ["{scope}"]\n---\n'


class MembershipTests(unittest.TestCase):
    """What makes a work item a team's work, with the areas of a scope given."""

    TEAM = {"approvers": ["@a"], "areas": ["payments"]}

    @staticmethod
    def areas(scope: list[str]) -> set[str]:
        return {"payments"} if any("billing" in p for p in scope) else set()

    CASES = (
        ("a Spec whose scope touches its area", {"type": "spec", "id": "SPEC-2", "tasks": [{"scope": ["src/billing/**"]}]}, True),
        ("a Spec elsewhere", {"type": "spec", "id": "SPEC-3", "parent": "INTENT-2", "tasks": [{"scope": ["web/**"]}]}, False),
        ("a Spec with no Tasks", {"type": "spec", "id": "SPEC-4"}, False),
        ("a Spec whose Tasks do not parse", {"type": "spec", "id": "SPEC-5", "tasks": "src/billing/**"}, False),
        ("a Task whose scope does not parse", {"type": "spec", "id": "SPEC-6", "tasks": [{"scope": "src/billing/**"}]}, False),
        ("a file of a type an Intent replaced", {"type": "epic", "id": "INTENT-1"}, False),
        ("a proposal", {"type": "proposal", "id": "PROP-1"}, False),
        ("a Spec whose delivery_team names the team", {"type": "spec", "id": "SPEC-7", "delivery_team": "payments"}, True),
        ("a Spec whose delivery_team names another team", {"type": "spec", "id": "SPEC-8", "delivery_team": "web"}, False),
        ("an Intent whose delivery_team names the team", {"type": "intent", "id": "INTENT-2", "delivery_team": "payments"}, True),
        ("an Intent whose delivery_team names another team", {"type": "intent", "id": "INTENT-3", "delivery_team": "web"}, False),
        ("an Intent that names no team", {"type": "intent", "id": "INTENT-4"}, False),
    )

    def test_each_item_is_the_teams_work_or_not(self):
        for what, data, expected in self.CASES:
            with self.subTest(what):
                self.assertIs(workitems.in_delivery_team(data, self.TEAM, self.areas, name="payments"), expected)

    def test_a_spec_is_its_intents_teams_work(self):
        intent = {"type": "intent", "id": "INTENT-1", "delivery_team": "payments"}
        spec_ = {"type": "spec", "id": "SPEC-1", "parent": "INTENT-1"}
        for parent, name, expected in ((intent, "payments", True), (intent, "web", False), (None, "payments", False)):
            self.assertIs(workitems.in_delivery_team(spec_, self.TEAM, self.areas, name=name, parent=parent), expected, (parent, name))

    def test_a_spec_that_names_its_own_team_is_not_its_intents_teams_work(self):
        intent = {"type": "intent", "id": "INTENT-1", "delivery_team": "web"}
        spec_ = {"type": "spec", "id": "SPEC-1", "parent": "INTENT-1", "delivery_team": "payments"}
        no_areas = {"approvers": ["@a"]}
        for name, expected in (("payments", True), ("web", False)):
            self.assertIs(workitems.in_delivery_team(spec_, no_areas, self.areas, name=name, parent=intent), expected, name)

    def test_a_team_with_no_areas_takes_no_spec_by_its_scope(self):
        self.assertFalse(
            workitems.in_delivery_team({"type": "spec", "tasks": [{"scope": ["src/billing/**"]}]}, {"approvers": ["@a"]}, self.areas, name="payments")
        )


class TeamRepo(unittest.TestCase):
    """A repository with three delivery teams and a few work items, run through the CLI."""

    CONFIG = teams(
        '  payments:\n    approvers: ["@a"]\n    areas: [payments]\n  web:\n    approvers: ["@b"]\n  both:\n    approvers: ["@c"]\n    areas: [payments]\n'
    )

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        for rel, text in self.files().items():
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text(text, encoding="utf-8")
        git(self.root, "init", "-q", "-b", "main")

    def files(self) -> dict[str, str]:
        return {
            ".aidd/config.yaml": self.CONFIG,
            "specs/INTENT-1.md": "---\ntype: intent\nid: INTENT-1\ntitle: e\ndelivery_team: web\ngoal: g\n---\n",
            "specs/SPEC-1.md": spec("SPEC-1", scope="src/billing/**"),
            "specs/SPEC-2.md": spec("SPEC-2", "parent: INTENT-1\n", "web/**"),
            "specs/SPEC-3.md": spec("SPEC-3", scope="docs/**"),
        }

    def cli(self, *argv: str) -> tuple[int, str]:
        here = os.getcwd()
        os.chdir(self.root)
        try:
            return run_cli(*argv)
        finally:
            os.chdir(here)


class ReferenceTests(TeamRepo):
    """A `delivery_team` on a Spec, an Intent, or a slice is checked against the keys of `delivery_teams`, and `aidd new` writes it."""

    def files(self):
        intent = "---\ntype: intent\nid: INTENT-1\ntitle: e\ndelivery_team: web\ngoal: g\nphases:\n  - id: P1\n    name: p\n    slices:\n"
        return {
            **super().files(),
            "specs/INTENT-1.md": intent + "      - {id: SPEC-9, title: s, delivery_team: wbe}\n---\n",
            "specs/SPEC-1.md": spec("SPEC-1", "delivery_team: payments\n", "src/billing/**"),
            "specs/SPEC-2.md": spec("SPEC-2", "delivery_team: paymnts\n", "web/**"),
        }

    def validate(self, rel: str) -> str:
        return self.cli("validate", rel)[1]

    def test_a_name_that_is_no_key_is_an_error_with_the_closest_key(self):
        said = self.validate("specs/SPEC-2.md")
        self.assertIn("delivery_team 'paymnts' is no key of the config's `delivery_teams`. Did you mean `payments`?", said)
        self.assertIn("slice SPEC-9 delivery_team 'wbe' is no key", self.validate("specs/INTENT-1.md"))

    def test_a_key_passes(self):
        self.assertNotIn("delivery_team", self.validate("specs/SPEC-1.md"))

    def test_new_writes_a_team_of_the_config_and_refuses_another(self):
        code, out = self.cli("new", "spec", "Pay", "--delivery-team", "payments", "--force")
        self.assertEqual(code, 0, out)
        written = (self.root / out.splitlines()[0].strip()).read_text(encoding="utf-8")
        self.assertIn("delivery_team: payments\n", written)
        self.assertNotIn("owner_team", written)
        self.assertNotEqual(self.cli("new", "spec", "Pay", "--delivery-team", "mobile")[0], 0)

    def test_new_names_a_team_of_the_config_on_a_proposal_a_runbook_and_a_postmortem(self):
        for kind, name in (("proposal", "PROP-1"), ("runbook", "RB-1"), ("postmortem", "PM-1")):
            with self.subTest(kind=kind):
                code, out = self.cli("new", kind, name, "--title", "t", "--delivery-team", "payments")
                self.assertEqual(code, 0, out)
                written = (self.root / out.splitlines()[0].strip()).read_text(encoding="utf-8")
                self.assertIn("\ndelivery_team: payments\n", written)
                self.assertNotIn("owner_team", written)
                code, out = self.cli("new", kind, name + "-2", "--title", "t", "--delivery-team", "mobile")
                self.assertNotEqual(code, 0)
                self.assertIn("payments", out)  # the error names the teams the config has

    def test_the_retired_flag_names_what_replaced_it_for_every_type(self):
        cases = (
            (("new", "runbook", "RB-1", "--title", "r", "--owner-team", "x"), ("--owner-team was retired in 1.0.0", "use --delivery-team")),
            (("new", "spec", "Pay", "--owner-team", "x"), ("--owner-team was retired in 1.0.0", "use --delivery-team")),
        )
        for argv, said in cases:
            with self.subTest(argv=argv):
                code, out = self.cli(*argv)
                self.assertNotEqual(code, 0, out)
                for words in said:
                    self.assertIn(words, out)

    def test_a_runbook_names_any_team_when_the_config_has_no_delivery_teams(self):
        (self.root / ".aidd/config.yaml").write_text(HEAD, encoding="utf-8")
        code, out = self.cli("new", "runbook", "RB-1", "--title", "r", "--delivery-team", "platform")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.cli("validate", out.splitlines()[0].strip())[1].count("delivery_team"), 0)
        code, out = self.cli("new", "spec", "Pay", "--delivery-team", "platform")
        self.assertNotEqual(code, 0, "a Spec's team is always a key of the config")


class TypedDocumentTeamTests(TeamRepo):
    """A runbook, a postmortem, or a proposal that names a team the config does not have is a warning, and never when the config
    has no `delivery_teams`, so a repository with one team is not asked to declare it."""

    DOCS = {
        "docs/runbooks/RB-1.md": "type: runbook\nid: RB-1\ntitle: t\nservice: s\ndelivery_team: {team}\nstatus: draft\n",
        "docs/postmortems/PM-1.md": 'type: postmortem\nid: PM-1\ntitle: t\nincident_on: "2026-09-01"\nseverity: sev2\ndelivery_team: {team}\nstatus: draft\n',
        "proposals/PROP-1/proposal.md": "type: proposal\nid: PROP-1\ntitle: t\naudience: internal\naddressee: a\ngoal: g\ndelivery_team: {team}\n",
    }

    def write(self, team: str, config_text: str | None = None) -> None:
        if config_text is not None:
            (self.root / ".aidd/config.yaml").write_text(config_text, encoding="utf-8")
        for rel, front in self.DOCS.items():
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text('---\naidd_version: "1.0.0"\n' + front.format(team=team) + "---\n\nbody\n", encoding="utf-8")

    def test_a_name_that_is_no_key_is_a_warning_with_the_closest_key(self):
        cases = (
            # (the team written, the config, whether each document is warned about it)
            ("paymnts", None, True),
            ("payments", None, False),
            ("TODO", None, False),  # `aidd new` writes a TODO to fill, which the placeholder check names
            ("anything", HEAD, False),  # a config with no `delivery_teams`
        )
        for team, config_text, warned in cases:
            with self.subTest(team=team, config=config_text is not None):
                self.write(team, config_text)
                for rel in self.DOCS:
                    code, said = self.cli("validate", rel)
                    line = f"warning: {rel}: delivery_team {team!r} is no key of the config's `delivery_teams`."
                    self.assertEqual(line in said, warned, said)
                    self.assertEqual(code, 0, said)  # a warning never fails
                    if warned:
                        self.assertIn("Did you mean `payments`?", said)


class StatusTests(TeamRepo):
    """`aidd status --delivery-team <name>` lists one team's open work, as text and as JSON."""

    CASES = (
        ("payments", ["SPEC-1"]),
        ("web", ["INTENT-1", "SPEC-2"]),
        ("both", ["SPEC-1"]),
    )

    def test_each_team_sees_its_own_work(self):
        for name, ids in self.CASES:
            with self.subTest(name):
                code, out = self.cli("status", "--delivery-team", name, "--json")
                self.assertEqual(code, 0, out)
                self.assertEqual(sorted(i["id"] for i in json.loads(out)["items"]), ids)
                code, out = self.cli("status", "--delivery-team", name)
                self.assertEqual(code, 0, out)
                shown = [line for line in out.splitlines() if not line.startswith((" ", "Your agent holds every open step"))]  # the last line may be the pick
                self.assertEqual(sorted(line.split()[0] for line in shown), ids)

    def test_without_the_flag_every_item_shows(self):
        code, out = self.cli("status", "--json")
        self.assertEqual(sorted(i["id"] for i in json.loads(out)["items"]), ["INTENT-1", "SPEC-1", "SPEC-2", "SPEC-3"])

    def test_an_intent_keeps_its_whole_progress(self):
        code, out = self.cli("status", "--delivery-team", "web", "--json")
        intent = next(i for i in json.loads(out)["items"] if i["id"] == "INTENT-1")
        self.assertEqual(intent["progress"], {"finished": 0, "total": 1})

    def test_another_teams_spec_still_blocks_one_of_this_teams(self):
        """The filter is a view: SPEC-1 (payments) blocks SPEC-2 (web), so web's SPEC-2 still reads as blocked."""
        path = self.root / "specs" / "SPEC-2.md"
        path.write_text(path.read_text(encoding="utf-8").replace("parent: INTENT-1\n", "parent: INTENT-1\nblocked_by: [SPEC-1]\n"), encoding="utf-8")
        code, out = self.cli("status", "--delivery-team", "web", "--json")
        item = next(i for i in json.loads(out)["items"] if i["id"] == "SPEC-2")
        self.assertEqual((item["blocked_by"], item["next"]["code"]), (["SPEC-1"], "spec.draft"))

    def test_a_team_the_config_does_not_name_is_an_error_that_names_the_teams(self):
        code, out = self.cli("status", "--delivery-team", "mobile")
        self.assertNotEqual(code, 0)
        self.assertIn("both, payments, web", out)


class TeamKeyTests(TeamRepo):
    """The answer says which teams each item is the work of, and the config's teams, so the work-items page can show a
    link, a filter, and a lane for each team by the one rule `--delivery-team` uses."""

    def files(self):
        return {**super().files(), "specs/SPEC-4.md": spec("SPEC-4", "delivery_team: web\n", "docs/**")}

    def items(self, *argv: str) -> dict[str, dict]:
        code, out = self.cli("status", "--json", *argv)
        self.assertEqual(code, 0, out)
        self.answer = json.loads(out)
        return {i["id"]: i for i in self.answer["items"]}

    def test_each_item_names_its_teams_by_the_rule_the_flag_uses(self):
        items = self.items()
        self.assertEqual(
            {k: v.get("teams_in_scope") for k, v in items.items()},
            {
                "INTENT-1": ["web"],
                "SPEC-1": ["payments", "both"],
                "SPEC-2": ["web"],
                "SPEC-3": None,
                "SPEC-4": ["web"],
            },
        )
        self.assertEqual(items["SPEC-4"]["delivery_team"], "web")

    def test_a_link_and_the_flag_show_the_same_items(self):
        for name in ("payments", "web", "both"):
            with self.subTest(name):
                everyone = self.items()
                teams_items = sorted(i for i, v in everyone.items() if name in v.get("teams_in_scope", []))
                self.assertEqual(sorted(self.items("--delivery-team", name)), teams_items)

    def test_the_top_lists_the_teams_in_the_configs_order_even_with_no_open_work(self):
        self.items()
        self.assertEqual(self.answer["delivery_teams"], ["payments", "web", "both"])
        self.items("--delivery-team", "payments")
        self.assertEqual(self.answer["delivery_teams"], ["payments", "web", "both"], "a filtered answer keeps every lane")
        (self.root / "specs" / "SPEC-1.md").unlink()
        self.items()
        self.assertEqual(self.answer["delivery_teams"], ["payments", "web", "both"])

    def test_without_delivery_teams_in_the_config_neither_key_shows(self):
        (self.root / ".aidd" / "config.yaml").write_text(HEAD, encoding="utf-8")
        items = self.items()
        self.assertNotIn("delivery_teams", self.answer)
        self.assertEqual([k for k, v in items.items() if "teams_in_scope" in v], [])
        self.assertEqual(json_schema.validate(self.answer, "status.schema.json"), [])

    def test_the_answer_with_teams_is_valid_under_the_schema(self):
        self.items()
        self.assertEqual(json_schema.validate(self.answer, "status.schema.json"), [])


if __name__ == "__main__":
    unittest.main()
