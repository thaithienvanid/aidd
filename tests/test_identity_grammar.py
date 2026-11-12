"""Who is a person and who is an agent has one grammar, stated once as data (`$defs/identity` in schemas/common.schema.json), and
one parser reads it (`config.typed_identity`). A control decides by it: who may say yes, who may triage, which role may suggest
work. A later reading may only refuse more: no identity that read as an agent on the commit before this grammar became data
(tests/fixtures/start-answers/identities.json) reads as a person now, or an agent's own words could count as a person's."""

import json
import unittest
from unittest import mock

import control_tables

from aidd import config
from aidd.kernel import resources
from aidd.workitems import handoff_notes, triage, work_list

START = {name: json.loads((control_tables.ANSWERS / f"{name}.json").read_text(encoding="utf-8")) for name in ("identities", "triage")}


class TheGrammarIsData(unittest.TestCase):
    def test_each_type_says_whether_it_names_a_person_or_an_agent_and_what_it_holds(self):
        identity = resources.load_json("common.schema.json")["$defs"]["identity"]
        self.assertEqual(config.identity_types(), identity["x-who"])
        self.assertEqual(set(identity["x-meanings"]), set(identity["x-who"]))
        self.assertEqual(set(identity["x-who"].values()) - {"person", "agent"}, set())
        for kind, meaning in identity["x-meanings"].items():
            self.assertTrue(meaning.startswith(f"`{kind}:<"), kind)

    def test_the_readers_follow_the_data_and_not_a_list_of_their_own(self):
        """A type the data marks as an agent's reads as an agent everywhere, and a type it drops is a tenant again."""
        moved = {"agent": "agent", "email": "person", "bot": "agent"}
        with mock.patch("aidd.config.identities.identity_types", return_value=moved):
            self.assertTrue(config.is_agent("bot:anything"))
            self.assertEqual(config.approved_by_kind("bot:anything"), "agent")
            self.assertEqual(config.typed_identity("bot:x"), ("bot", "x"))
            self.assertEqual(config.typed_identity("role:x"), (None, "x"), "without the type, `role` reads as a tenant")

    def test_the_parser_reads_the_type_as_is_agent_does(self):
        cases = {
            "role:architect": ("role", "architect"),
            "Role:Architect": ("role", "architect"),
            "ｒole:architect": ("role", "architect"),
            "ro​le:architect": ("role", "architect"),
            "acme:role:architect": ("role", "architect"),
            "acme:agent:claude-code/x": ("agent", "claude-code/x"),
            "email:a@b.c": ("email", "a@b.c"),
            "@alice": (None, "alice"),
            "acme:@alice": (None, "alice"),
            "Jean:Paul": (None, "paul"),
            "": (None, ""),
        }
        for written, expected in cases.items():
            with self.subTest(ascii(written)):
                self.assertEqual(config.typed_identity(written), expected)


class AReadingOnlyRefusesMore(unittest.TestCase):
    def test_no_identity_that_read_as_an_agent_reads_as_a_person(self):
        self.assertEqual(sorted(START["identities"]), sorted(control_tables.identities()), "the table and its answers are one set")
        for written, then in START["identities"].items():
            with self.subTest(ascii(written)):
                if then["is_agent"]:
                    self.assertTrue(config.is_agent(written))
                if then["approved_by_kind"] is not None:
                    self.assertIsNotNone(config.approved_by_kind(written), "a value refused as an approver is refused still")
                if then["approved_by_kind"] == "agent":
                    self.assertEqual(config.approved_by_kind(written), "agent")

    def test_honest_identities_still_read_as_people(self):
        """A person's name with a colon, an address, a team, a tenant's login, and names in another alphabet or with accents."""
        people = ("@alice", "@org/team", "email:alice@example.com", "acme:@alice", "Jean:Paul", "José García <jose@example.com>", "@josé", "Nguyễn")
        for who in people:
            with self.subTest(who):
                self.assertFalse(config.is_agent(who))
                self.assertFalse(START["identities"].get(who, {"is_agent": False})["is_agent"])
        for who in ("José García <jose@example.com>", "Devin Lee <devin@example.com>", "@org/team", "email:alice@example.com"):
            self.assertIsNone(config.approved_by_kind(who), who)

    def test_a_tenant_named_like_a_type_reads_as_the_type(self):
        """`email`, `agent`, and `role` are never tenants: `role:alice` is a role, so its holder can never say yes (fail-closed)."""
        for kind in config.identity_types():
            self.assertEqual(config.typed_identity(f"{kind}:alice")[0], kind)
        self.assertTrue(config.is_agent("role:alice"))
        self.assertEqual(config.approved_by_kind("role:alice"), "agent")


def errors_now(case: str) -> int:
    data, proactive = control_tables.triage_cases()[case]
    return len(triage.triage_errors(data, proactive=proactive))


class TheTriageRule(unittest.TestCase):
    def test_every_error_the_rule_gave_it_still_gives(self):
        self.assertEqual(sorted(START["triage"]), sorted(control_tables.triage_cases()))
        for case, then in START["triage"].items():
            with self.subTest(case):
                self.assertGreaterEqual(errors_now(case), then)

    def test_a_role_written_as_today_decides_as_its_old_form_did(self):
        for case, then in START["triage"].items():
            who = json.loads(case)[0]
            role = who.removeprefix("agent:")
            if who.startswith("agent:") and "/" not in role and role in resources.load_json("roles.json")["roles"]:
                with self.subTest(case):
                    self.assertEqual(errors_now(case.replace(json.dumps(who), json.dumps(f"role:{role}"), 1)), then)

    def test_only_the_exact_form_of_an_allowed_role_suggests(self):
        allowed = ["architect"]
        for who, refused in {
            "role:architect": False,
            "agent:architect": True,
            "Role:architect": True,
            "acme:role:architect": True,
            "ｒole:architect": True,
            "role:developer": True,
            "agent:claude-code/claude-opus-5-5": True,
            "dependabot[bot]": False,
            "@alice": False,
        }.items():
            with self.subTest(ascii(who)):
                said = triage.triage_errors({"type": "spec", "suggested_by": who}, proactive=allowed)
                self.assertEqual(any("may not suggest work" in e for e in said), refused)

    def test_a_role_suggestion_waits_for_a_person(self):
        """The revert proof of `role:`: were `is_agent` to stop reading it, this Spec would read as a person's and skip triage."""
        data = {"type": "spec", "id": "SPEC-1", "suggested_by": "role:architect", "status": "ready"}
        self.assertTrue(any("needs triage" in e for e in triage.triage_errors(data)))
        self.assertEqual(work_list.spec_step(data, "ready", [], None)["code"], "spec.triage")


class TheHandoffNotesBy(unittest.TestCase):
    def note(self, by: str) -> list[str]:
        text = f"```aidd-handoff\ndone: d\nnext_role: verifier\nneeds: none\nstopped_at: none\nby: {by}\n```\n"
        return [w for w in handoff_notes.handoff_warnings("specs/SPEC-1.md", text) if "names a role" in w]

    def test_a_role_in_by_is_named_because_by_says_who_ran_it(self):
        self.assertEqual(len(self.note("role:developer")), 1)
        self.assertEqual(self.note("agent:claude-code/claude-opus-5-5"), [])
        self.assertEqual(self.note('"@alice"'), [])


if __name__ == "__main__":
    unittest.main()
