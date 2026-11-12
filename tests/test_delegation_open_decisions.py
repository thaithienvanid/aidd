"""A role's `open_decisions` entry holds a delegated Spec approval or merge until a later handoff note answers it, and
`aidd status` shows where each answer stands. Invariant: under a delegation, Spec approval and a merge defer while any note
the check reads holds an entry that no later note answers with `answered: [{id, choice}]`, its own `id` and one of its own
choices written exactly. Text on `decided` answers nothing. A note is an agent's text, so an entry only adds a defer: the
field left out or empty asks nothing, and an entry that does not read stays open."""

import tempfile
import unittest
from pathlib import Path

from helpers import SAMPLE_SPEC, git
from test_delegation_check import Repo, codes, note
from test_delegation_spec import SpecCase

from aidd import workitems
from aidd.delegation import action_checks
from aidd.delegation.check import Check, Request
from aidd.kernel import json_schema, resources, strict_yaml
from aidd.workitems import handoff_notes, work_list

RISK = "the new check fails a branch that has no tests"
OTHER = "the cache keeps a stale page for an hour"
OPTIONS = [{"choice": "warn only", "blocks": "nothing"}, {"choice": "fail the run", "blocks": "a docs-only change"}]


def entry(ident: object = "no-tests", what: object = RISK, options: object = OPTIONS) -> dict:
    return {**({"id": ident} if ident is not None else {}), "what": what, "options": options}


def answer(ident: str = "no-tests", choice: str = "warn only") -> dict:
    return {"id": ident, "choice": choice}


def block(**fields) -> str:
    """One `aidd-handoff` block with the four keys a note needs and `fields`."""
    return "```aidd-handoff\n" + strict_yaml.dump({"done": "built it", "next_role": "verifier", "needs": "none", "stopped_at": "none", **fields}) + "```\n"


def raw_block(body: str) -> str:
    return f"```aidd-handoff\ndone: built it\nnext_role: verifier\nneeds: none\nstopped_at: none\n{body}\n```\n"


def states(*notes: str) -> tuple[list[tuple], int]:
    """Each entry that reads as (id, status, choice), and how many entries do not read, over the notes in order."""
    found, unreadable = workitems.decision_states(workitems.handoff_blocks("\n".join(notes)))
    return [(s["entry"]["id"], s["status"], s.get("choice")) for s in found], len(unreadable)


ASK = block(open_decisions=[entry()])
OPEN = ([("no-tests", "open", None)], 0)
ANSWERED = ([("no-tests", "answered", "warn only")], 0)


class DecisionStateTests(unittest.TestCase):
    def test_an_entry_is_answered_only_by_its_id_and_one_of_its_own_choices_on_a_later_note(self):
        cases = {  # the notes, in order -> (each entry that reads as (id, status, choice), the entries that do not read)
            "no field": ([block()], ([], 0)),
            "an empty list": ([raw_block("open_decisions: []")], ([], 0)),
            "one entry on the latest note": ([ASK], OPEN),
            "many entries": (
                [block(open_decisions=[entry(), entry("cache", OTHER), entry("third", "a third")])],
                ([("no-tests", "open", None), ("cache", "open", None), ("third", "open", None)], 0),
            ),
            "an entry in an older note only": ([ASK, block(done="merged")], OPEN),
            "a later note answers it by id and an offered choice": ([ASK, block(answered=[answer()])], ANSWERED),
            "the answer two notes later": ([ASK, block(), block(answered=[answer()])], ANSWERED),
            "one of two answered": (
                [block(open_decisions=[entry(), entry("cache", OTHER)]), block(answered=[answer()])],
                ([("no-tests", "answered", "warn only"), ("cache", "open", None)], 0),
            ),
            "the same id in two notes, one answer both offer clears the newest only": (
                [ASK, ASK, block(answered=[answer()])],
                ([("no-tests", "open", None), ("no-tests", "answered", "warn only")], 0),
            ),
            "the same id in two notes, two answers clear both": (
                [ASK, ASK, block(answered=[answer()]), block(answered=[answer()])],
                ([("no-tests", "answered", "warn only")] * 2, 0),
            ),
            "the same id in two notes, an answer between them clears the first only": (
                [ASK, block(answered=[answer()]), ASK],
                ([("no-tests", "answered", "warn only"), ("no-tests", "open", None)], 0),
            ),
            "the same id, an answer only the older entry offers": (
                [
                    ASK,
                    block(open_decisions=[entry(options=[{"choice": "drop it", "blocks": "x"}, {"choice": "keep it", "blocks": "y"}])]),
                    block(answered=[answer()]),
                ],
                ([("no-tests", "answered", "warn only"), ("no-tests", "open", None)], 0),
            ),
            "the same id in three notes, two answers in one note clear one": (
                [ASK, ASK, ASK, block(answered=[answer(), answer()])],
                ([("no-tests", "open", None), ("no-tests", "open", None), ("no-tests", "answered", "warn only")], 0),
            ),
            "a later needs names the id": ([ASK, block(needs="Pick one for no-tests.")], ([("no-tests", "needs_person", None)], 0)),
            "a later needs names a longer id only": ([ASK, block(needs="Pick one for no-tests-two")], OPEN),
            "an answer after the needs": ([ASK, block(needs="Pick one for no-tests"), block(answered=[answer()])], ANSWERED),
            # fail closed: each of these stays open
            "prose on decided that holds the what": ([ASK, block(decided=[f"{RISK}: warn only"])], OPEN),
            "prose on decided that names the id and the choice": ([ASK, block(decided=["no-tests: warn only"])], OPEN),
            "an answer in the entry's own note": ([block(open_decisions=[entry()], answered=[answer()])], OPEN),
            "an answer in an earlier note": ([block(answered=[answer()]), ASK], OPEN),
            "an answer with a choice the entry did not offer": ([ASK, block(answered=[answer(choice="drop it")])], OPEN),
            "an answer with the choice in another case": ([ASK, block(answered=[answer(choice="Warn only")])], OPEN),
            "an answer that names another id": ([ASK, block(answered=[answer("cache")])], OPEN),
            "one note answers the id twice, two ways": ([ASK, block(answered=[answer(), answer(choice="fail the run")])], OPEN),
            "one note answers the id twice, one way": ([ASK, block(answered=[answer(), answer()])], ANSWERED),
            "an answered that is no list": ([ASK, raw_block("answered: no-tests")], OPEN),
            "an answer with no choice": ([ASK, block(answered=[{"id": "no-tests"}])], OPEN),
            "a later note that does not parse answers nothing": ([ASK, "```aidd-handoff\nanswered: [{id: no-tests\n```\n"], OPEN),
            # entries that do not read
            "an entry with no id, as a note written before ids": ([block(open_decisions=[entry(None)]), block(answered=[answer()])], ([], 1)),
            "an id that is no id": ([block(open_decisions=[entry("no tests")])], ([], 1)),
            "two entries with one id in a note": ([block(open_decisions=[entry(), entry(what=OTHER)]), block(answered=[answer()])], ([], 2)),
            "an entry with one choice": ([block(open_decisions=[entry(options=OPTIONS[:1])])], ([], 1)),
            "an entry whose two choices are one": ([block(open_decisions=[entry(options=[OPTIONS[0], OPTIONS[0]])])], ([], 1)),
            "a field with no value, so the note does not parse": ([raw_block("open_decisions:")], ([], 1)),
            "a field that is a string": ([raw_block("open_decisions: a risk")], ([], 1)),
            "an entry that is a string": ([raw_block("open_decisions: [a risk]")], ([], 1)),
            "an entry with no what": ([block(open_decisions=[{"id": "no-tests", "options": OPTIONS}])], ([], 1)),
            "a blank what": ([block(open_decisions=[entry(what="  ")])], ([], 1)),
            "a what that is a number": ([block(open_decisions=[entry(what=7)])], ([], 1)),
            "a note that does not parse and names the field": (["```aidd-handoff\nopen_decisions: [\n```\n"], ([], 1)),
            "a note that does not parse and names no field": (["```aidd-handoff\ndone: [\n```\n"], ([], 0)),
        }
        for name, (notes, expected) in cases.items():
            with self.subTest(name):
                self.assertEqual(states(*notes), expected)


def decided(texts: dict[str, str], action: str = "pr.merge") -> list[str]:
    check = Check(Request(action=action))
    action_checks.decisions_check(check, texts)
    return codes({"reasons": check.reasons})


class SharedIdTests(unittest.TestCase):
    """Two roles that name a decision alike (`approach`, a or b) are two decisions: one answer clears one, and the check holds
    the merge for the other."""

    def test_one_answer_leaves_the_second_decision_open_and_two_answers_clear_both(self):
        pick = [{"choice": "a", "blocks": "nothing"}, {"choice": "b", "blocks": "a docs-only change"}]
        role = block(open_decisions=[entry("approach", "how to cache", pick)])
        cases = {
            "no answer": ([role, role], ["note_open_decision"]),
            "one answer": ([role, role, block(answered=[answer("approach", "a")])], ["note_open_decision"]),
            "two answers in two notes": ([role, role, block(answered=[answer("approach", "a")]), block(answered=[answer("approach", "b")])], []),
            "one answer for each of two ids": (
                [
                    block(open_decisions=[entry("approach", "x", pick), entry("other", "y", pick)]),
                    block(answered=[answer("approach", "a"), answer("other", "b")]),
                ],
                [],
            ),
        }
        for name, (notes, expected) in cases.items():
            with self.subTest(name):
                self.assertEqual(decided({"the Spec": "\n".join(notes)}), expected)


def noted(*texts: str, head: str = "a" * 12) -> list[str]:
    """The codes `notes_check` defers with, for notes in the order the check reads them."""
    check = Check(Request(action="pr.merge", head=head))
    action_checks.notes_check(check, {f"text {i}": t for i, t in enumerate(texts)})
    return codes({"reasons": check.reasons})


class LaterNoteTests(unittest.TestCase):
    """Invariant: a note after the one that names the head either reads and names a head, or the check defers. A note can only
    narrow what is allowed, so a note the check cannot read must stop it, never be skipped to an older `needs: none`."""

    def test_a_later_note_that_does_not_read_or_names_no_head_defers(self):
        good = block(head="a" * 12)
        cases = {
            "one good note": ([good], []),
            "good, then good": ([good, block(head="a" * 12)], []),
            "good, then a note that does not parse": ([good, "```aidd-handoff\nneeds: the person picks X: now\n```\n"], ["note_unreadable"]),
            "good, then a note with no head": ([good, block()], ["note_unreadable"]),
            "good, then a note whose YAML is no mapping": ([good, "```aidd-handoff\n- a\n- b\n```\n"], ["note_unreadable"]),
            "a note that does not parse, then a good one": (["```aidd-handoff\nneeds: [\n```\n", good], []),
            "a note with no head, then a good one": ([block(), good], []),
            "good, a bad one, then a good one": ([good, block(), block(head="a" * 12)], []),
            "good, then a bad one, in another text": ([good, "", block()], ["note_unreadable"]),
            "no note names a head": ([block()], ["note_missing"]),
        }
        for name, (texts, expected) in cases.items():
            with self.subTest(name):
                self.assertEqual(noted(*texts), expected)


class ReadingOrderTests(unittest.TestCase):
    """The check reads the notes of the Spec, then the pull request's body, then the head commit's message, as it reads the
    latest note: a later text answers an earlier one, never the other way round."""

    def test_a_later_text_answers_an_earlier_one(self):
        ask = block(open_decisions=[entry()], head="a" * 12)
        reply = block(answered=[answer()], head="b" * 12)
        cases = {
            "no note anywhere": ({"the Spec": "", "the pull request's body": "", "the head commit's message": ""}, []),
            "the Spec's entry, answered in the pull request's body": ({"the Spec": ask, "the pull request's body": reply, "the head commit's message": ""}, []),
            "the Spec's entry, answered in the head commit": ({"the Spec": ask, "the pull request's body": "", "the head commit's message": reply}, []),
            "the body's entry, answered only in the Spec before it": (
                {"the Spec": reply, "the pull request's body": ask, "the head commit's message": ""},
                ["note_open_decision"],
            ),
            "an entry on a note that names another commit": (
                {"the Spec": ask, "the pull request's body": block(head="b" * 12), "the head commit's message": ""},
                ["note_open_decision"],
            ),
            "a Spec approval reads the Spec alone": ({"the Spec": ask + reply}, []),
        }
        for name, (texts, expected) in cases.items():
            with self.subTest(name):
                self.assertEqual(decided(texts), expected)

    def test_the_reason_names_each_open_id_with_its_choices_and_each_entry_that_does_not_read(self):
        check = Check(Request(action="pr.merge"))
        notes = block(open_decisions=[entry(), entry("cache", OTHER), entry(None, "a third")]) + block(needs="Pick one for cache")
        action_checks.decisions_check(check, {"the Spec": notes})
        self.assertEqual(len(check.reasons), 1)
        detail = check.reasons[0]["detail"]
        for said in ("`no-tests` is open", "'warn only', 'fail the run'", "`cache` waits for a person's choice", "has no `id`"):
            self.assertIn(said, detail)
        self.assertFalse(check.reasons[0]["reserved"], "the lead can answer it, so it is no person's alone")


class LocalMergeTests(SpecCase):
    """A local merge reads the notes in the head commit's message: the role's entry holds it, and the lead's answer frees it."""

    def head(self, repo: Repo, *notes: str) -> str:
        repo.write("src/app.py", "print('hello, world')\n")
        code = repo.commit("Say hello to the world")
        named = [n.replace("head: HEAD\n", 'head: "HEAD"\n').replace('"HEAD"', f'"{code}"') for n in notes]
        head = repo.commit("Hand off", "-m", "\n".join(named))
        git(self.root, "checkout", "-q", "main")
        return head

    def test_an_open_decision_holds_the_merge_until_the_lead_answers_it(self):
        role = block(open_decisions=[entry()], head="HEAD")
        cases = {
            "the role's entry, then the verifier's note": ([role, note("HEAD")], ["note_open_decision"]),
            "the lead's later note answers it by id and choice": ([role, block(answered=[answer()], head="HEAD")], []),
            "the lead's later note answers it in prose": ([role, block(decided=[f"{RISK}: warn only"], head="HEAD")], ["note_open_decision"]),
            "no entry at all": ([note("HEAD")], []),
        }
        for name, (notes, expected) in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                self.root = Path(d).resolve()
                repo = self.repo()
                result = repo.check(self.head(repo, *notes))
                self.assertEqual(codes(result), expected)
                for reason in result["reasons"]:
                    self.assertIn("`no-tests` is open", reason["detail"], "the role's note read, and its entry is named")


class BrokenBaseConfigTests(SpecCase):
    """With no remote, a default branch whose config does not load stops the check on that cause, so the person meets the
    step that works: they fix the config and merge that change themselves, since no head vouches for its own config."""

    def test_a_config_that_does_not_load_on_the_default_branch_is_named_as_the_cause(self):
        repo = self.repo()
        git(self.root, "checkout", "-q", "main")
        repo.write(".aidd/config.yaml", 'aidd_version: "1.0.0"\nprofile: [\n')
        repo.commit("break the config")
        git(self.root, "checkout", "-q", "feature")
        git(self.root, "merge", "-q", "--no-edit", "main")
        repair = repo.commit("Repair the config")
        git(self.root, "checkout", "-q", "main")
        result = repo.check(repair)
        self.assertEqual(codes(result), ["config_unreadable"])
        self.assertIn("main", result["reasons"][0]["detail"], "the reason names the branch whose config does not load")


class SpecApprovalTests(SpecCase):
    """An architect's entry in the Spec holds its delegated approval until a later note in the Spec answers it."""

    def test_an_open_decision_in_the_spec_holds_its_approval(self):
        spec = SAMPLE_SPEC.replace("route: normal", "status: ready\nroute: normal")
        role = block(open_decisions=[entry()], next_role="architect")
        cases = {
            "an unanswered entry": (spec + "\n" + role, ["note_open_decision"]),
            "an entry the lead answered by id and choice": (spec + "\n" + role + block(answered=[answer()]), []),
        }
        for name, (text, expected) in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                self.root = Path(d).resolve()
                repo, head = self.spec_repo(spec_text=text)
                self.assertEqual(codes(self.approve(repo, head)), expected)


class ValidateTests(unittest.TestCase):
    """`aidd validate` warns about each answer the check would not count, in one file, so a lead learns it at write time."""

    def test_each_answer_the_check_would_not_count_is_one_warning(self):
        cases = {  # the file's notes -> the words of the one warning, or None for none
            "a good answer": ([ASK, block(answered=[answer()])], None),
            "an answer to an entry the file does not hold": ([block(answered=[answer()])], None),
            "two entries with one id": ([block(open_decisions=[entry(), entry(what=OTHER)])], "two open_decisions entries have the id `no-tests`"),
            "an answer in the entry's own note": ([block(open_decisions=[entry()], answered=[answer()])], "which its own note or a later one holds"),
            "an answer before the entry": ([block(answered=[answer()]), ASK], "which its own note or a later one holds"),
            "a choice the entry did not offer": ([ASK, block(answered=[answer(choice="drop it")])], "which note 1 does not offer"),
            "one id in two notes": ([ASK, block(done="again"), ASK], "entries in notes 1, 3 share the id `no-tests`: give each decision its own id"),
            "one id in two notes, answered between them": ([ASK, block(answered=[answer()]), ASK], "entries in notes 1, 3 share the id `no-tests`"),
        }
        for name, (notes, said) in cases.items():
            with self.subTest(name):
                found = [w for w in handoff_notes.handoff_warnings("specs/SPEC-1.md", "\n".join(notes)) if "open_decisions" in w or "answers" in w]
                self.assertEqual(len(found), 0 if said is None else 1, found)
                if said:
                    self.assertIn(said, found[0])

    def test_an_entry_with_no_id_is_a_schema_warning(self):
        found = handoff_notes.handoff_warnings("specs/SPEC-1.md", block(open_decisions=[entry(None)]))
        self.assertTrue([w for w in found if "open_decisions" in w and "id" in w], found)


class StatusTests(unittest.TestCase):
    """`aidd status` shows each entry with its id, its choices, and where its answer stands, and `--json` holds it in the
    shape schemas/status.schema.json gives."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()

    def tearDown(self):
        self.tmp.cleanup()

    def open_work(self, notes: str) -> dict:
        (self.root / "specs").mkdir(exist_ok=True)
        (self.root / "specs/SPEC-220.md").write_text(SAMPLE_SPEC + "\n" + notes, encoding="utf-8")
        return workitems.open_work(self.root, None)

    def test_each_entry_shows_with_its_id_its_choices_and_its_answer(self):
        cases = {
            "no field": (block(), None, []),
            "an open entry": (ASK, [{"entry": entry(), "status": "open"}], ["decision no-tests, open", "warn only (blocks: nothing)"]),
            "an answered entry": (
                ASK + block(answered=[answer()]),
                [{"entry": entry(), "status": "answered", "choice": "warn only"}],
                ["decision no-tests, answered: warn only"],
            ),
            "an entry a person chooses": (
                ASK + block(needs="Pick one for no-tests"),
                [{"entry": entry(), "status": "needs_person"}],
                ["decision no-tests, a person chooses"],
            ),
            "an entry with no id is left to aidd validate": (block(open_decisions=[entry(None)]), None, []),
        }
        for name, (notes, expected, lines) in cases.items():
            with self.subTest(name):
                work = self.open_work(notes)
                item = next(i for i in work["items"] if i["id"] == "SPEC-220")
                self.assertEqual(item.get("open_decisions"), expected)
                self.assertEqual(json_schema.validate({"schema_version": "1", **work, "findings": []}, "status.schema.json"), [])
                text = workitems.status_text(work)
                for line in lines:
                    self.assertIn(line, text)
                self.assertEqual(RISK in text, bool(expected))

    def test_the_text_reads_every_state_the_schema_lists(self):
        schema = resources.load_json("status.schema.json")["$defs"]["open_decision_state"]["properties"]["status"]["enum"]
        self.assertEqual(list(work_list._DECISION_SAID), schema)

    def test_the_last_commits_note_shows_its_entries(self):
        """A change with no Spec keeps its note in its last commit's message, so `handoff` carries its entries there."""
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "-c", "user.name=Maya", "-c", "user.email=m@example.com", "commit", "-q", "--allow-empty", "-m", "start")
        git(self.root, "checkout", "-qb", "feature")
        notes = block(open_decisions=[entry(), entry("cache", OTHER)]) + block(answered=[answer("cache", "fail the run")])
        git(self.root, "-c", "user.name=Maya", "-c", "user.email=m@example.com", "commit", "-q", "--allow-empty", "-m", "Hand off", "-m", notes)
        work = workitems.open_work(self.root, None)
        workitems.add_branch_facts(self.root, work)
        self.assertEqual(
            work["handoff"]["open_decisions"],
            [{"entry": entry(), "status": "open"}, {"entry": entry("cache", OTHER), "status": "answered", "choice": "fail the run"}],
        )
        self.assertEqual(json_schema.validate({"schema_version": "1", **work, "findings": []}, "status.schema.json"), [])
        self.assertIn("decision cache, answered: fail the run", workitems.status_text(work))


if __name__ == "__main__":
    unittest.main()
