"""The reader decides the level: the plain-language practice skill, and the client-document, existing-system, and speed
references that lean on it.

These tests pin what must be there (a level per doc kind, the three levels, the measured and the reviewed rules, the
registry entries, one owner per fact), not how a sentence reads. The new text is also held to its own level, STE-80:
no sentence over 35 words, at least 90% at 25 words or fewer, and an average of 20 or fewer.
"""

from __future__ import annotations

import re
import unittest

from helpers import ROOT
from test_plain_language import sentences

from aidd import evals, knowledge, packs, resources

TEAM = ROOT / "plugins" / "aidd-team"
SKILLS = TEAM / "skills"
PLAIN = SKILLS / "plain-language" / "SKILL.md"
CLIENT = SKILLS / "client-delivery"
ESTIMATION = SKILLS / "estimation"
GENERATED = re.compile(r"<!-- aidd:gen [^>]*-->.*?<!-- aidd:end -->", re.S)
FRONT = re.compile(r"\A---\n.*?\n---\n", re.S)

# The text this change wrote, held to STE-80. Each file is read without its front matter and its generated blocks.
NEW_TEXT = (
    PLAIN,
    CLIENT / "references" / "client-documents.md",
    CLIENT / "references" / "verify-what-exists.md",
    ESTIMATION / "references" / "speed-band.md",
    TEAM / "commands" / "refine.md",
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
    """One table maps doc kinds to three levels; an unlisted kind is ste-80, and a person may ask for any level."""

    def test_the_three_levels_and_their_readers(self):
        text = read(PLAIN)
        table = [r for r in packs.section(text, "Implement").splitlines() if r.startswith("| `")]
        levels = [r.split("|")[1].strip() for r in table]
        self.assertEqual(levels, ["`ste-80`", "`plain`", "`ste-100`"])
        ste80, plain, ste100 = table
        for kind in ("runbooks", "rollback", "onboarding", "handoffs", "Specs", "approval text", "digests", "CLI messages", "templates"):
            self.assertIn(kind, ste80, kind)
        for kind in ("proposals", "contracts", "change orders", "client status", "release notes"):
            self.assertIn(kind, plain, kind)
        self.assertIn("`[project.writing] ste_100`", ste100)
        self.assertIn("inside the team", ste80)
        self.assertIn("outside the team", plain)

    def test_no_global_default_and_a_person_may_ask(self):
        text = read(PLAIN)
        self.assertIn("no global default", text)
        self.assertRegex(text, r"A kind the table does not list is `ste-80`")
        self.assertIn("A person may ask for any level", text)

    def test_ste_80_states_its_rules_and_does_not_stretch_the_numbers(self):
        text = " ".join(read(PLAIN).split())
        for must in (
            "20 words or fewer",
            "25 words or fewer",
            "one instruction",
            "active voice",
            "GLOSSARY.md",
            "one word, one meaning",
            "90%",
            "35 words",
            "15 to 20",
            "ceilings",
            "about 6 sentences",
            "without its dictionary",
        ):
            self.assertIn(must, text, must)
        # Never split a sentence where a qualifier or a reference would be lost; a list keeps them.
        for word in ('"only"', '"unless"', '"otherwise"', '"it"', '"there"', "list"):
            self.assertIn(word, packs.section(read(PLAIN), "Implement"), word)
        self.assertIn("does not stretch the numbers", text)

    def test_ste_100_dictionary_is_the_projects(self):
        text = " ".join(read(PLAIN).split()).casefold()
        self.assertIn("the project supplies the dictionary", text)
        self.assertIn("aidd never includes it", text)

    def test_every_level_keeps_the_exact_text_and_the_warnings(self):
        text = packs.section(read(PLAIN), "Implement")
        for must in ("Never paraphrase", "code", "commands", "paths", "URLs", "exact errors", "quotes", "full sentences", "irreversible", "structured data"):
            self.assertIn(must, text, must)


class CheckTests(unittest.TestCase):
    """A pinned Vale rule per level measures sentence length; the skill names what only a review can check."""

    def test_the_vale_row_is_pinned_and_has_one_rule_per_level(self):
        row = next(r for r in packs.section(read(PLAIN), "Test commands").splitlines() if r.startswith("| Sentence length"))
        self.assertRegex(row, r"`vale` \(v\d+\.\d+\.\d+\)")
        for must in ("extends: occurrence", "scope: sentence", "max:", "`ste-80`", "`plain`", "`ste-100`", ".vale.ini"):
            self.assertIn(must, row, must)
        # The pin is the one the registry checked for the prose linter.
        docs_test = raw()["standards"]["docs-under-test-every-code-sample"]["edition"]
        self.assertIn(re.search(r"v\d+\.\d+\.\d+", row).group(0), docs_test)

    def test_the_35_word_cap_gives_the_right_reason(self):
        review = " ".join(packs.section(read(PLAIN), "Review").split())
        self.assertIn("because up to 10% of the sentences may pass their limit, and no sentence may pass 35", review)
        self.assertNotIn("allows 10% over the limit", review)

    def test_the_skill_says_what_is_measured_and_what_is_reviewed(self):
        review = packs.section(read(PLAIN), "Review")
        self.assertIn("**Measured", review)
        self.assertIn("**By review", review)
        for must in ("instruction", "active voice", "glossary", "dictionary"):
            self.assertIn(must, review.split("**By review", 1)[1], must)


class RegistryTests(unittest.TestCase):
    def test_the_practice_entry_and_its_steward(self):
        entry = raw()["practices"]["plain-language"]
        self.assertEqual(entry["steward"], "@thaithienvanid")
        self.assertLessEqual({"asd-ste100", "iso-24495-plain-language"}, ids(entry["standards"]))
        self.assertLessEqual(len(entry["standards"]), packs.PACK_STANDARDS)

    def test_each_standard_is_cited_in_the_skill(self):
        body = read(PLAIN).split("<!-- aidd:end -->", 1)[1]
        for cite in ("ASD-STE100", "ISO 24495-1", "Vale"):
            self.assertIn(cite, body, cite)

    def test_the_new_entries_carry_evidence_that_confirms_them(self):
        table = raw()["standards"]
        for sid in ("asd-ste100", "iso-24495-plain-language"):
            s = table[sid]
            with self.subTest(sid=sid):
                self.assertEqual(s["checked"], "2026-10-02")
                self.assertEqual(s["evidence"]["retrieved"], "2026-10-02")
                self.assertTrue(evals.confirms(s), sid)
        self.assertIn("Issue 9", table["asd-ste100"]["edition"])
        self.assertTrue(table["asd-ste100"]["evidence"]["url"].startswith("https://www.asd-ste100.org/"))
        # iso.org answers a script with a challenge page, so the evidence is the national body's official page. The
        # notes hold only what a reader of the standard needs; the history of the check is in the commit message.
        iso = table["iso-24495-plain-language"]
        self.assertNotIn("iso.org", iso["evidence"]["url"])
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
        self.assertEqual(sorted(p.name for p in folder.rglob("*") if p.is_file()), ["SKILL.md"])

    def test_no_role_preloads_it(self):
        roles = resources.roles()["roles"]
        for key, r in roles.items():
            self.assertNotIn("plain-language", r["preload"], key)
        writers = {k for k, r in roles.items() if "plain-language" in r["practices"]}
        self.assertLessEqual({"tech-writer", "delivery-manager", "product-manager"}, writers)

    def test_the_offline_currency_check_reads_both_entries(self):
        where = {(s.get("id"), s["where"]) for s in evals.standards()}
        self.assertIn(("asd-ste100", "practice plain-language"), where)
        self.assertIn(("iso-24495-plain-language", "practice plain-language"), where)
        self.assertIn("asd-ste100", {e["id"] for e in knowledge.evidence_entries()})


class OneOwnerTests(unittest.TestCase):
    """Technical writing and client delivery point to the levels instead of restating them."""

    def test_technical_writing_points_to_it(self):
        text = read(SKILLS / "technical-writing" / "SKILL.md")
        self.assertIn("`aidd-team:plain-language`", text)
        self.assertNotIn("One idea per sentence, active voice, second person, present tense", text)
        self.assertNotIn("iso-24495-plain-language", ids(raw()["practices"]["technical-writing"]["standards"]))
        row = next(r for r in packs.section(text, "Test commands").splitlines() if r.startswith("| Reading-level check"))
        # One owner for the reader's level: the row measures a grade, and the level comes from plain-language.
        self.assertIn("`aidd-team:plain-language`", row)
        self.assertNotIn("Sentence length", packs.practice_tests(text))

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
        for must in ("on request", "3blue1brown", "single html file", "one idea per slide", "step by step", "before", "after", "light and dark", "pdf"):
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
        for must in ("1.5×", "2×", "2.5×", "3×", "normal pace", "port", "names its cuts"):
            self.assertIn(must, text, must)

    def test_the_band_maps_to_the_estimate_the_right_way_round(self):
        # The estimate's low, likely, and high are effort or duration, low <= likely <= high. A bigger speed-up gives
        # a shorter duration, so the ceiling gives `low` and the minimum gives `high`.
        rows = {
            r.split("|")[1].strip(): r for r in packs.section(read(ESTIMATION / "references" / "speed-band.md"), "The band").splitlines() if r.startswith("| ")
        }
        self.assertIn("3×", rows["Ceiling"])
        self.assertIn("`low`", rows["Ceiling"])
        self.assertIn("2×", rows["Target"])
        self.assertIn("`likely`", rows["Target"])
        self.assertIn("1.5×", rows["Minimum"])
        self.assertIn("`high`", rows["Minimum"])
        text = " ".join(read(ESTIMATION / "references" / "speed-band.md").split())
        self.assertIn("shortest", text)
        self.assertIn("longest", text)

    def test_the_band_is_the_teams_choice(self):
        text = " ".join(read(ESTIMATION / "references" / "speed-band.md").split())
        self.assertIn("design choice", text)
        self.assertIn("not a published figure", text)
        self.assertIn("owner", text)

    def test_the_lead_time_is_per_change_and_the_project_date_is_the_initiatives(self):
        text = " ".join(read(ESTIMATION / "references" / "speed-band.md").split())
        self.assertIn("first gate run", text)
        self.assertIn("first pass", text)
        self.assertIn("each change", text)
        self.assertIn("Initiative", text)
        self.assertIn("milestones", text)
        self.assertIn("`--dora --specs", text)

    def test_what_never_compresses_and_how_speed_counts(self):
        text = " ".join(read(ESTIMATION / "references" / "speed-band.md").split())
        self.assertIn("human testing", text.casefold())
        for must in ("review", "external waits", "never compressed", "never shorter than the external waits"):
            self.assertIn(must, text, must)
        for must in ("lead time", "first-pass share", "change failure rate", "time to restore", "`aidd metrics`", "A/B"):
            self.assertIn(must, text, must)
        self.assertIn("references/speed-band.md", read(ESTIMATION / "SKILL.md"))


class OwnLevelTests(unittest.TestCase):
    """The new text is written at STE-80."""

    def test_new_text_is_ste_80(self):
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
