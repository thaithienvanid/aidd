"""The reader decides the level: the plain-language practice skill, and the client-document, existing-system, and speed
references that lean on it.

These tests pin what must be there (a level per doc type, the three levels, the measured and the reviewed rules, the
registry entries, one owner per fact), not how a sentence reads. The skill's own text is also held to its level, `instruction`:
no sentence over 35 words, at least 90% at 25 words or fewer, and an average of 20 or fewer. The limits, the examples,
and the proof of each rule are in test_plain_language_proof.py.
"""

from __future__ import annotations

import re
import unittest

from helpers import ROOT, says
from test_plain_language import sentences

from aidd.knowledge import evidence_recheck
from aidd.evals import standards_audit
from aidd.docsgen import pack_budget
from aidd.knowledge import standards_evidence, team_registry
from aidd.kernel import documents, resources

TEAM = ROOT / "plugins" / "aidd-team"
SKILLS = TEAM / "skills"
PLAIN = SKILLS / "plain-language" / "SKILL.md"
CLIENT = SKILLS / "client-delivery"
ESTIMATION = SKILLS / "estimation"
GENERATED = re.compile(r"<!-- aidd:gen [^>]*-->.*?<!-- aidd:end -->", re.S)
FRONT = re.compile(r"\A---\n.*?\n---\n", re.S)

# The text of the plain-language skill and of the files that lean on it, held to `instruction`. Each file is read without its
# front matter and its generated blocks.
NEW_TEXT = (
    PLAIN,
    PLAIN.parent / "references" / "examples.md",
    PLAIN.parent / "references" / "voice.md",
    PLAIN.parent / "references" / "ux-copy.md",
    CLIENT / "references" / "client-documents.md",
    CLIENT / "references" / "verify-what-exists.md",
    ESTIMATION / "references" / "speed-band.md",
    TEAM / "commands" / "plan.md",  # its Refine mode was a command of its own
)


def read(path) -> str:
    return path.read_text(encoding="utf-8")


def prose(path) -> str:
    return GENERATED.sub("", FRONT.sub("", read(path)))


def raw() -> dict:
    return resources.load_json("roles.json")


def ids(refs: list) -> set[str]:
    return {r if isinstance(r, str) else r["id"] for r in refs}


class LevelTests(unittest.TestCase):
    """One table maps doc types to three levels; an unlisted type is instruction, and a person may ask for any level."""

    def test_the_three_levels_and_their_readers(self):
        text = read(PLAIN)
        table = [r for r in documents.raw_section(text, "Implement").splitlines() if r.startswith("| `")]
        levels = [r.split("|")[1].strip() for r in table]
        self.assertEqual(levels, ["`instruction`", "`plain`", "`controlled`"])
        instruction, plain, controlled = table
        for doc_type in ("runbooks", "rollback", "onboarding", "handoffs", "Specs", "approval text", "CLI messages", "templates", "normative rules"):
            self.assertIn(doc_type, instruction, doc_type)
        # What the text does sets the level: text that explains, such as a guide or a digest, is `plain`.
        for doc_type in ("READMEs", "guides", "changelogs", "digests", "proposals", "contracts", "change orders", "client status", "release notes"):
            self.assertIn(doc_type, plain, doc_type)
        self.assertIn("`project.writing.controlled`", controlled)
        self.assertIn("inside the team", instruction)
        self.assertIn("outside the team", plain)

    def test_no_global_default_and_a_person_may_ask(self):
        text = read(PLAIN)
        self.assertIn("no global default", text)
        self.assertRegex(text, r"A type the table does not list is `instruction`")
        self.assertIn("A person may ask for any level", text)

    def test_agent_text_and_customer_messages_have_a_level(self):
        """Text an agent reads is `instruction`, and a message a customer reads is `plain`: what the text does sets the level."""
        table = [r for r in documents.raw_section(read(PLAIN), "Implement").splitlines() if r.startswith("| `")]
        instruction, plain, _ = table
        for doc_type in ("agent files", "skills", "prompts", "without its dictionary"):
            self.assertIn(doc_type, instruction, doc_type)
        self.assertIn("messages a customer reads", plain)

    def test_controlled_dictionary_is_the_projects(self):
        text = " ".join(read(PLAIN).split()).casefold()
        self.assertIn("the project supplies the dictionary", text)
        self.assertIn("aidd never includes it", text)

    def test_every_level_keeps_the_exact_text_and_the_warnings(self):
        text = documents.raw_section(read(PLAIN), "Implement")
        for must in ("Never paraphrase", "code", "commands", "paths", "URLs", "exact errors", "quotes", "full sentences", "irreversible", "structured data"):
            self.assertIn(must, text, must)


class CheckTests(unittest.TestCase):
    """A pinned Vale rule per level measures sentence length; the skill names what only a review can check."""

    def test_the_vale_row_is_pinned_and_has_one_rule_per_level(self):
        row = next(r for r in documents.raw_section(read(PLAIN), "Test commands").splitlines() if r.startswith("| Sentence length"))
        self.assertRegex(row, r"`vale` \(v\d+\.\d+\.\d+\)")
        for must in ("extends: occurrence", "scope: sentence", "max:", "`instruction`", "`plain`", "`controlled`", ".vale.ini"):
            self.assertIn(must, row, must)
        # The pin is the one the registry checked for the prose linter.
        docs_test = raw()["standards"]["docs-under-test-every-code-sample"]["edition"]
        self.assertIn(re.search(r"v\d+\.\d+\.\d+", row).group(0), docs_test)

    def test_the_35_word_cap_gives_the_right_reason(self):
        """Vale holds the 35 alone because it cannot count the 10% share; the other limits are for review."""
        text = " ".join(documents.raw_section(read(PLAIN), "Implement").split())
        self.assertTrue(says(text, "Vale cannot count a share", "35"), text)

    def test_the_review_is_an_ordered_procedure_that_starts_with_the_measure(self):
        review = documents.raw_section(read(PLAIN), "Review")
        steps = re.findall(r"^(\d+)\. (.*)$", review, re.M)
        self.assertEqual([n for n, _ in steps], [str(i) for i in range(1, len(steps) + 1)])
        self.assertIn("Vale", steps[0][1])
        for must in ("writing level", "glossary", "dictionary", "claim", "reader"):
            self.assertIn(must, review, must)


class RegistryTests(unittest.TestCase):
    def test_the_practice_entry_names_its_standards(self):
        entry = raw()["practices"]["plain-language"]
        self.assertNotIn("steward", entry)  # aidd names no steward of its own; an adopter may name one
        self.assertLessEqual({"asd-ste100", "iso-24495-plain-language"}, ids(entry["standards"]))
        self.assertLessEqual(len(entry["standards"]), pack_budget.PACK_STANDARDS)

    def test_each_standard_is_cited_in_the_skill(self):
        body = read(PLAIN).split("<!-- aidd:end -->", 1)[1]
        for cite in ("ASD-STE100", "ISO 24495-1", "Vale"):
            self.assertIn(cite, body, cite)

    def test_the_new_entries_carry_a_citation_that_confirms_them(self):
        table = raw()["standards"]
        for sid in ("asd-ste100", "iso-24495-plain-language"):
            s = table[sid]
            with self.subTest(sid=sid):
                # Checked when added (2026-10-02) or re-checked since: the date and the read are one.
                self.assertGreaterEqual(s["checked"], "2026-10-02")
                self.assertTrue(standards_audit.confirms(s), sid)
        self.assertIn("Issue 9", table["asd-ste100"]["edition"])
        self.assertTrue(table["asd-ste100"]["citation"]["url"].startswith("https://www.asd-ste100.org/"))
        # iso.org answers a script with a challenge page, so the citation is the national body's official page. The
        # notes hold only what a reader of the standard needs; the history of the check is in the commit message.
        iso = table["iso-24495-plain-language"]
        self.assertNotIn("iso.org", iso["citation"]["url"])
        self.assertNotIn("403", iso["notes"])
        self.assertIn("relevant, findable, understandable, usable", iso["notes"])

    def test_the_sentence_limits_have_secondary_support(self):
        # The limits are in the standard, which is free only on request; a public secondary source quotes them.
        notes = raw()["standards"]["asd-ste100"]["notes"]
        self.assertIn("https://en.wikipedia.org/wiki/Simplified_Technical_English", notes)
        self.assertIn('"Write short sentences: no more than 20 words in instructions (procedures) and 25 words in descriptive texts."', notes)
        self.assertIn("read 2026-10-02", notes)

    def test_the_skill_ships_no_dictionary(self):
        folder = SKILLS / "plain-language"
        files = sorted(str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file())
        self.assertEqual(files, ["SKILL.md", "references/examples.md", "references/ux-copy.md", "references/voice.md"])  # no dictionary
        self.assertFalse([f for f in files if "dictionar" in f.lower() or "approved-words" in f.lower()])

    def test_no_role_preloads_it(self):
        roles = team_registry.roles()["roles"]
        for key, r in roles.items():
            self.assertNotIn("plain-language", r["preload"], key)
        writers = {k for k, r in roles.items() if "plain-language" in r["practices"]}
        self.assertLessEqual({"tech-writer", "delivery-manager", "product-manager"}, writers)

    def test_the_offline_currency_check_reads_both_entries(self):
        where = {(s.get("id"), s["where"]) for s in standards_evidence.dated_entries()}
        self.assertIn(("asd-ste100", "practice plain-language"), where)
        self.assertIn(("iso-24495-plain-language", "practice plain-language"), where)
        self.assertIn("asd-ste100", {e["id"] for e in evidence_recheck.citation_entries()})


class OneOwnerTests(unittest.TestCase):
    """Technical writing and client delivery point to the levels instead of restating them."""

    def test_technical_writing_points_to_it(self):
        text = read(SKILLS / "technical-writing" / "SKILL.md")
        self.assertIn("`aidd-team:plain-language`", text)
        self.assertNotIn("One idea per sentence, active voice, second person, present tense", text)
        self.assertNotIn("iso-24495-plain-language", ids(raw()["practices"]["technical-writing"]["standards"]))
        row = next(r for r in documents.raw_section(text, "Test commands").splitlines() if r.startswith("| Reading-level check"))
        # One owner for the reader's level: the row measures a grade, and the level comes from plain-language.
        self.assertIn("`aidd-team:plain-language`", row)
        self.assertNotIn("Sentence length", pack_budget.practice_tests(text))

    def test_client_delivery_points_to_it_and_to_its_references(self):
        text = read(CLIENT / "SKILL.md")
        self.assertIn("`aidd-team:plain-language`", text)
        for ref in ("references/client-documents.md", "references/verify-what-exists.md"):
            self.assertIn(f"({ref})", text, ref)


class ClientDocumentsTests(unittest.TestCase):
    def test_the_nothing_misleading_pass(self):
        text = " ".join(read(CLIENT / "references" / "client-documents.md").split()).casefold()
        for must in (
            "before sign-off",
            "every",
            "same",
            "never",
            "already works",
            "matching evidence",
            "simulator",
            "real device",
            "exceptions",
            "third party",
        ):
            self.assertIn(must, text, must)

    def test_dates_decisions_and_numbers(self):
        text = " ".join(read(CLIENT / "references" / "client-documents.md").split()).casefold()
        for must in ("likely", "committed", "contingency", "already decided for you", "lives in one document", "never restate"):
            self.assertIn(must, text, must)

    def test_the_explainer_deck_is_disposable(self):
        text = " ".join(read(CLIENT / "references" / "client-documents.md").split()).casefold()
        for must in ("on request", "single html file", "one idea per slide", "step by step", "before", "after", "light and dark", "pdf"):
            self.assertIn(must, text, must)
        self.assertIn("never the record and never evidence", text)


class VerifyWhatExistsTests(unittest.TestCase):
    def test_current_behaviour_with_its_place_in_the_code(self):
        text = " ".join(read(CLIENT / "references" / "verify-what-exists.md").split())
        for must in ("before", "scope", "`file:line`", '"not in code"', "stub", "hidden", "flag", "cites"):
            self.assertIn(must, text, must)


class SpeedBandTests(unittest.TestCase):
    def test_the_band(self):
        text = " ".join(read(ESTIMATION / "references" / "speed-band.md").split())
        for must in ("1×", "2×", "2.5×", "3×", "normal pace", "port", "names its cuts"):
            self.assertIn(must, text, must)

    def test_the_band_maps_to_the_estimate_the_right_way_round(self):
        # The estimate's low, likely, and high are effort or duration, low <= likely <= high. A bigger speed-up gives
        # a shorter duration, so the ceiling gives `low` and the minimum gives `high`.
        rows = {
            r.split("|")[1].strip(): r
            for r in documents.raw_section(read(ESTIMATION / "references" / "speed-band.md"), "The band").splitlines()
            if r.startswith("| ")
        }
        self.assertIn("3×", rows["Ceiling"])
        self.assertIn("`low`", rows["Ceiling"])
        self.assertIn("2×", rows["Target"])
        self.assertIn("`likely`", rows["Target"])
        self.assertIn("1×", rows["Minimum"])
        self.assertIn("`high`", rows["Minimum"])
        text = " ".join(read(ESTIMATION / "references" / "speed-band.md").split())
        self.assertIn("shortest", text)
        self.assertIn("longest", text)

    def test_the_band_is_the_teams_choice(self):
        text = " ".join(read(ESTIMATION / "references" / "speed-band.md").split())
        self.assertIn("design choice", text)
        self.assertIn("not a published figure", text)
        self.assertIn("owner", text)

    def test_the_lead_time_is_per_change_and_the_project_date_is_the_intents(self):
        text = " ".join(read(ESTIMATION / "references" / "speed-band.md").split())
        self.assertIn("first CI run", text)
        self.assertIn("first-pass share", text)
        self.assertIn("Each change's lead time", text)
        self.assertIn("Intent", text)
        self.assertIn("phases", text)
        self.assertIn("from its first commit to its merge", text)

    def test_what_never_compresses_and_how_speed_counts(self):
        text = " ".join(read(ESTIMATION / "references" / "speed-band.md").split())
        self.assertIn("human testing", text.casefold())
        for must in ("review", "external waits", "never compressed", "never shorter than the external waits"):
            self.assertIn(must, text, must)
        for must in ("lead time", "first-pass share", "change failure rate", "time to restore", "`rolled_back`", "A/B"):
            self.assertIn(must, text, must)
        self.assertIn("references/speed-band.md", read(ESTIMATION / "SKILL.md"))


class OwnLevelTests(unittest.TestCase):
    """The skill and the files that lean on it are written at `instruction`."""

    def test_new_text_is_instruction_level(self):
        for path in NEW_TEXT:
            with self.subTest(path=path.relative_to(ROOT)):
                found = sentences(prose(path))
                self.assertGreater(len(found), 5)
                self.assertEqual([s for n, s in found if n > 35], [])
                short = sum(1 for n, _ in found if n <= 25)
                self.assertGreaterEqual(short / len(found), 0.9, sorted(found, reverse=True)[:5])
                self.assertLessEqual(sum(n for n, _ in found) / len(found), 20, sorted(found, reverse=True)[:5])


if __name__ == "__main__":
    unittest.main()
