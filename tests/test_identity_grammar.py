"""Who is a person and who is an agent has one grammar, stated once as data (`$defs/identity` in schemas/common.schema.json), and
one parser reads it (`config.typed_identity`). A control decides by it: who may say yes, who may triage, which role may suggest
work. A later reading may only refuse more: no identity that read as an agent on the commit before this grammar became data
(tests/fixtures/start-answers/identities.json) reads as a person now, or an agent's own words could count as a person's."""

import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import control_tables

from aidd import config
from aidd.kernel import resources
from aidd.workitems import approval, handoff_notes, intent_checks, triage, work_list

START = {name: json.loads((control_tables.ANSWERS / f"{name}.json").read_text(encoding="utf-8")) for name in ("identities", "triage")}

# One normalising step reads every name before it is compared as a whole (`identities._squash`, `_name_parts`): runs of spaces and tabs, `-`,
# `_`, `,`, and `;` between words are one space, a `.` or `!` at the end is gone, and a part in round brackets is a whole name of its own.
SQUASHED_AGENTS = (
    "Claude  Code",
    "Claude\tCode",
    "Claude.",
    "Codex.",
    "Devin AI.",
    "Claude Code!",
    "GitHub  Copilot",
    "Claude-Code",
    "Claude_Code",
    "GitHub-Copilot",
    "Cursor-Agent",
    "Claude , Code",
    "Maya (aider)",
    "Maya (Claude Code)",
    "Jane Roe (Claude Code)",
    "Maya (aider",
    "Maya ((aider))",
    "Bot.",
)
SQUASHED_PEOPLE = (
    "Lee, Devin",
    "Monet, Claude",
    "Devin Lee, PhD",
    "Claude Monet; Acme",
    "Cody Bot-Hansen",
    "Claude M.",
    "Devin Lee (he/him)",
    "Maya (Mai) Lee",
    "Claude Code Smith",
    "Gemini Okafor",
    "Codex Alvarez",
    "Junie Park",
    "Kiro Tanaka",
    "Amazon Q. Lee",
)
# Reads as a person today: a stated limit. A listed name that stands beside other words is no listed name: the words follow it, or a person's
# name comes first with a comma or a semicolon. The owner kept the limit (SECURITY.md). A later rule about such a name changes this one table.
STATED_LIMIT = (
    "Claude Bot",
    "Claude Code Bot",
    "Claude Opus 4.5",
    "Codex Agent",
    "Copilot Agent",
    "Copilot Chat",
    "Gemini CLI",
    "Roo Code",
    "Jane Roe, Claude Code",
    "Jane Roe; Codex",
)


# An approver an agent's name or an agent's address makes a refusal, with the ways the refusal names that pass the door: a surname, an initial, or an
# address of their own (`config.one_word_hint`). `email:<address>` is a way only where the door takes it.
REFUSED_WITH_WAYS = (
    ("Claude <claude@example.com>", ("Claude Smith <claude@example.com>", "Claude S. <claude@example.com>"), "email:claude@example.com"),
    ("Claude Code <jane@example.com>", ("Claude Code Smith <jane@example.com>", "Claude Code S. <jane@example.com>"), "email:jane@example.com"),
    ("Jane Roe <noreply@anthropic.com>", ("Jane Roe <jane@example.com>",), "email:jane@example.com"),
)


def git_name_accepted(root: Path, name: str, email: str) -> bool:
    """Whether `aidd approve` takes git's `name` and `email` as the approver: `approval._identity`, the one reader of git's identity."""
    subprocess.run(["git", "config", "user.name", name], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", email], cwd=root, check=True)
    try:
        approval._identity(root)
    except ValueError:
        return False
    return True


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

    def test_a_plain_agent_name_reads_as_an_agent_in_every_reader_and_a_person_who_shares_a_word_does_not(self):
        """A name is judged as a whole, never by a part: the product's name alone, with its vendor's, or a generic `bot` or `agent` is an
        agent's; a name that only holds such a word is a person's. `approver_is_agent` and `approved_by_kind` read one list of whole
        names, so a waiver, a delegation, an Intent's approval, and a Spec's `approved_by` agree."""
        agents = [
            "Claude Code <person@example.com>",
            "Claude Agent <person@example.com>",
            "OpenAI Codex <person@example.com>",
            "GitHub Copilot <person@example.com>",
            "Cursor Agent <person@example.com>",
            "Devin AI <person@example.com>",
            "Google Antigravity <person@example.com>",
            "bot <x@example.com>",
            "agent <x@example.com>",
            "BOT <x@example.com>",
            "bot",
            "agent",
        ]
        people = [
            "Abbot Lee <a@example.com>",
            "Agent Smith <smith@example.com>",
            "Devin Lee <devin@example.com>",
            "Claude Monet <monet@example.com>",
            "Cody Bot-Hansen <c@example.com>",
            "agent.smith@example.com",
            "lee+bot@example.com",
            "José García <jose@example.com>",
            "Claude the agent <person@example.com>",  # only a part of the name says agent, and a part is never judged
        ]
        for who in agents:
            with self.subTest(agent=who):
                self.assertTrue(config.approver_is_agent(who))
                self.assertEqual(config.approved_by_kind(who), "agent")
        for who in people[:-1]:
            with self.subTest(person=who):
                self.assertFalse(config.approver_is_agent(who))
                self.assertIn(config.approved_by_kind(who), (None, "form"))
        self.assertFalse(config.approver_is_agent(people[-1]), "a part of a name is never judged, so this stays a person's, on purpose")

    def test_every_door_reads_a_name_after_the_one_normalising_step(self):
        """Each of the doors reads the same name the same way: the waivers, a delegation, an Intent's approval, and a Spec's `approved_by`
        through `approved_by_kind` and `approver_is_agent`, and `aidd approve` through git's identity (`approval._identity`)."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            for is_agent, names in ((True, SQUASHED_AGENTS), (False, SQUASHED_PEOPLE)):
                for name in names:
                    who = f"{name} <jane@example.com>"
                    with self.subTest(name=name, agent=is_agent):
                        self.assertEqual(config.approved_by_kind(who), "agent" if is_agent else None)
                        self.assertEqual(config.approver_is_agent(who), is_agent)
                        self.assertEqual(git_name_accepted(root, name, "jane@example.com"), not is_agent)
                        if is_agent:
                            self.assertTrue(config.is_agent(who))
            for name in STATED_LIMIT:  # reads as a person today: a stated limit
                with self.subTest(stated_limit=name):
                    self.assertIsNone(config.approved_by_kind(f"{name} <jane@example.com>"))
                    self.assertTrue(git_name_accepted(root, name, "jane@example.com"))

    def test_each_door_that_refuses_an_agents_name_names_the_way_out_and_the_way_passes_that_door(self):
        """The Spec's `approved_by`, an Intent's `approval.by`, and `aidd approve` say how a person whose name or address reads as an agent's gets
        through, by the one sentence `one_word_hint` gives; each way it names is tried at that door. `aidd approve` takes git's name and address, so it
        names no `email:`. The waiver, the delegation, `--approvers`, and `aidd init --delegate` try theirs in their own tests."""

        def intent(who: str) -> str:
            found = intent_checks.approval_problems("I.md", {"type": "intent", "approval": {"by": who, "at": "2026-11-10T09:12:00Z"}})
            return "\n".join(e for e in found if not e.startswith("warning"))

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            subprocess.run(["git", "init", "-q", str(root)], check=True)

            def approve(who: str) -> str:
                name, _, email = who.partition(" <")
                return "" if git_name_accepted(root, name, email.removesuffix(">")) else self.approve_message(root)

            doors = {
                "approved_by": (lambda who: config.approved_by_problem(who) or "", True),
                "intent": (intent, True),
                "aidd approve": (approve, False),
            }
            for door, (refuse, takes_email) in doors.items():
                for who, ways, email_way in REFUSED_WITH_WAYS:
                    with self.subTest(door=door, who=who):
                        message = refuse(who)
                        self.assertIn(config.one_word_hint(takes_email), message)
                        for way in ways:
                            self.assertEqual(refuse(way), "", way)
                        if takes_email:
                            self.assertEqual(refuse(email_way), "", email_way)
                        else:
                            self.assertNotIn("email:", message)

    @staticmethod
    def approve_message(root: Path) -> str:
        try:
            approval._identity(root)
        except ValueError as refused:
            return str(refused)
        return ""

    def test_a_note_in_the_name_is_in_no_form_and_an_agents_word_in_it_still_refuses(self):
        """More than six words with a comma, a semicolon, or a bracket is a note, as before: a form warning, and an agent where it holds an agent's word."""
        note = "Maya, as the owner's delegate (record of 2026-11-07)"
        self.assertEqual(config.approved_by_kind(f"{note} <maya@example.com>"), "form")
        self.assertEqual(config.approved_by_kind(f"{note.replace('Maya', 'Claude')} <maya@example.com>"), "agent")

    def test_a_name_with_many_brackets_is_read_in_one_pass(self):
        started = time.monotonic()
        self.assertTrue(config.approver_is_agent("(" * 200_000 + "aider"))
        self.assertFalse(config.approver_is_agent("Maya (" * 20_000 + "Lee)"), "a part that is no agent's name stays a person's")
        self.assertLess(time.monotonic() - started, 5)

    def test_an_address_of_an_agent_account_at_githubs_no_reply_domain_is_an_agents_under_any_name(self):
        agents = (
            "12345+Copilot@users.noreply.github.com",
            "9+COPILOT@users.noreply.github.com",
            "12345+copilot-swe-agent@users.noreply.github.com",
            "12345+copilot-swe-agent[bot]@users.noreply.github.com",
            "12345+copilot-pull-request-reviewer@users.noreply.github.com",
        )
        people = (
            "12345+jane@users.noreply.github.com",
            "12345+claude@users.noreply.github.com",  # a login that is no account of the list is a person's
            "jane+copilot@users.noreply.github.com",  # no number before the `+`
            "12345+copilot@example.com",  # not GitHub's domain
        )
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            for is_agent, addresses in ((True, agents), (False, people)):
                for address in addresses:
                    for name in ("Jane Roe", "Maya Lee"):
                        with self.subTest(address=address, name=name):
                            self.assertEqual(config.approver_is_agent(f"{name} <{address}>"), is_agent)
                            self.assertEqual(git_name_accepted(root, name, address), not is_agent)
                    with self.subTest(address=address, form="email:"):
                        self.assertEqual(config.approver_is_agent(f"email:{address}"), is_agent)

    def test_the_identity_aidd_approve_reads_from_git_is_judged_by_the_approver_rule_like_every_other_door(self):
        """A person whose name holds an agent's word is accepted; every agent form stays refused. `aidd approve` is not run: its one reader of git's identity is."""
        accepted = [
            ("Maya Lee", "maya@example.com"),
            ("Devin Lee", "devin@example.com"),
            ("Claude Monet", "monet@example.com"),
            ("Copilot Charlie", "charlie@example.com"),
            ("Cursor Jones", "jones@example.com"),
            ("Agent Smith", "smith@example.com"),
            ("Abbot Lee", "a@example.com"),
            ("José García", "jose@example.com"),
            ("Lee, Devin", "lee@example.com"),
            ("Devin Lee (he/him)", "devin@example.com"),
            ("Gemini Okafor", "g@example.com"),
            ("Codex Alvarez", "c@example.com"),
            ("Junie Park", "j@example.com"),
            ("Kiro Tanaka", "k@example.com"),
            ("Amazon Q. Lee", "a@example.com"),
        ]
        refused = [
            ("Claude Code", "person@example.com"),
            ("GitHub Copilot", "p@example.com"),
            ("bot", "x@example.com"),
            ("agent", "x@example.com"),
            ("Claude", "noreply@anthropic.com"),
            ("Maya", "noreply@anthropic.com"),
            ("agent:developer", "d@example.com"),
            ("dependabot[bot]", "49699333+dependabot[bot]@users.noreply.github.com"),
            ("github-actions[bot]", "github-actions[bot]@users.noreply.github.com"),
            ("Cl\u200baude", "c@example.com"),
            ("Claude  Code", "c@example.com"),
            ("Claude.", "c@example.com"),
            ("Claude-Code", "c@example.com"),
            ("Maya (aider)", "maya@example.com"),
            ("Jane Roe", "12345+Copilot@users.noreply.github.com"),
        ]
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            for expected, rows in ((True, accepted), (False, refused)):
                for name, email in rows:
                    with self.subTest(name=name, email=email):
                        subprocess.run(["git", "config", "user.name", name], cwd=root, check=True)
                        subprocess.run(["git", "config", "user.email", email], cwd=root, check=True)
                        if expected:
                            self.assertEqual(approval._identity(root), f"{name} <{email}>")
                        else:
                            with self.assertRaises(ValueError):
                                approval._identity(root)

    def test_each_list_of_the_agent_names_is_alphabetical_as_the_file_says(self):
        """`schemas/agents.json` says every list is alphabetical, so a new name goes where the alphabet puts it."""
        known = resources.load_json("agents.json")
        self.assertIn("alphabetical", known["description"])
        lists = {"agent_accounts": known["agent_accounts"], **{f"agent_coauthors.{k}": v for k, v in known["agent_coauthors"].items()}}
        self.assertEqual(
            sorted(lists),
            sorted(["agent_accounts", "agent_coauthors.emails", "agent_coauthors.email_patterns", "agent_coauthors.names", "agent_coauthors.full_names"]),
        )
        for where, items in lists.items():
            with self.subTest(where):
                self.assertEqual(items, sorted(items))

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
