"""`aidd explain <word>`: what one of aidd's words means and why, read from the data that owns it. Each answer is text its
source holds, the kinds come in one order, and an unknown word says how to list the known ones."""

import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from helpers import make_repo, run_cli

from aidd import knowledge
from aidd.kernel import json_schema, resources


def explain(*argv: str, cwd: Path | None = None) -> tuple[int, str]:
    here = os.getcwd()
    os.chdir(cwd or here)
    try:
        return run_cli("explain", *argv)
    finally:
        os.chdir(here)


class ExplainTests(unittest.TestCase):
    def test_each_kind_answers_from_the_file_that_owns_it(self):
        risks, common = resources.load_json("risks.json"), resources.load_json("common.schema.json")["$defs"]
        roles = resources.load_json("roles.json")
        cases = [
            # (the word, its kind, the text its source holds, the source)
            ("pr.merge", "action", risks["actions"]["pr.merge"]["description"], "schemas/risks.json"),
            ("auth", "area", risks["areas"]["auth"]["description"], "schemas/risks.json"),
            ("major", "route", common["route"]["x-meanings"]["major"], "schemas/common.schema.json"),
            ("Specify", "loop_step", "In Specify", "schemas/roles.json"),
            ("Spec approval", "decision", "what one change does", "schemas/roles.json"),
            ("verifier", "role", roles["roles"]["verifier"]["does"].split(". ")[0], "schemas/roles.json"),
            ("tech-spec", "document_type", roles["graph"]["documents"]["tech-spec"]["home"], "schemas/roles.json"),
            ("In-Progress", "status", common["status"]["x-meanings"]["in_progress"], "schemas/common.schema.json"),
            ("solo", "profile", resources.load_json("profiles.json")["profiles"]["solo"]["description"], "schemas/profiles.json"),
        ]
        for word, kind, quoted, source in cases:
            found = [m for m in knowledge.explain(word) if m["type"] == kind]
            self.assertEqual(len(found), 1, (word, kind))
            self.assertIn(quoted.rstrip("."), found[0]["what"], word)
            self.assertEqual(found[0]["source"], source, word)

    def test_the_word_for_each_type_and_each_level_answers_from_its_schema(self):
        """`aidd explain ask` and `aidd explain level` are the first thing a person types after reading a risk answer."""
        risks = resources.load_json("risks.schema.json")
        owners = {
            "action": "schemas/risks.schema.json",
            "area": "schemas/risks.schema.json",
            "level": "schemas/risks.schema.json",
            "route": "schemas/common.schema.json",
            "profile": "schemas/profiles.json",
        }
        for word, source in owners.items():
            with self.subTest(word=word):
                found = [m for m in knowledge.explain(word) if m["type"] == word]
                self.assertEqual([m["source"] for m in found], [source])
                self.assertTrue(found[0]["what"])
        for level in risks["$defs"]["level"]["enum"]:
            with self.subTest(level=level):
                found = knowledge.explain(level)
                self.assertEqual([m["type"] for m in found], ["level"])
                meaning = re.search(rf"\b{level}: ([^.]*)", risks["$defs"]["level"]["description"]).group(1)
                self.assertIn(meaning, found[0]["what"])

    def test_a_word_close_to_none_gets_no_guess_and_the_way_to_search(self):
        for word in ("flibbertigibbet", "xyzzy", "routing"):  # "routing" is only 0.67 like `route`: a different word
            with self.subTest(word=word):
                code, out = explain(word)
                self.assertEqual(code, 2)
                self.assertNotIn("Did you mean", out)
                self.assertIn("aidd recall", out)

    def test_an_action_says_the_rule_in_force_and_what_its_level_does(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d) / "repo", "solo", branch=None)
            code, out = explain("pr.merge", "--json", cwd=root)
        data = json.loads(out)
        self.assertEqual((code, json_schema.validate(data, "explain.schema.json")), (0, []))
        why = data["matches"][0]["why"]
        self.assertTrue(why.startswith("pr.merge: ask"), why)
        meaning = re.search(r"\bask: ([^.]*)", resources.load_json("risks.schema.json")["$defs"]["level"]["description"]).group(1)
        self.assertIn(meaning, why)

    def test_a_word_of_two_kinds_gives_both_in_the_kinds_order(self):
        kinds = [m["type"] for m in knowledge.explain("Plan")]
        self.assertEqual(kinds, ["stage", "loop_step"])
        self.assertEqual(kinds, sorted(kinds, key=knowledge.EXPLAIN_TYPES.index))

    def test_the_schema_lists_the_kinds_in_the_order_answers_give_them(self):
        kinds = resources.load_json("explain.schema.json")["$defs"]["type"]["enum"]
        self.assertEqual(kinds, list(knowledge.EXPLAIN_TYPES))

    def test_an_unknown_word_exits_2_and_names_the_list(self):
        with tempfile.TemporaryDirectory() as d:
            code, out = explain("flibbertigibbet", "--json", cwd=Path(d))
            self.assertEqual((code, json.loads(out[: out.index("\naidd explain:")])["matches"]), (2, []))
            code, out = explain("flibbertigibbet", cwd=Path(d))
        self.assertEqual(code, 2)
        self.assertIn("aidd explain --list", out)

    def test_the_list_covers_every_kind_and_validates(self):
        with tempfile.TemporaryDirectory() as d:
            code, out = explain("--list", "--json", cwd=Path(d))
        data = json.loads(out)
        self.assertEqual((code, json_schema.validate(data, "explain.schema.json")), (0, []))
        self.assertEqual(list(data["words"]), list(knowledge.EXPLAIN_TYPES))
        self.assertTrue(all(data["words"].values()), "every kind has a word")


GLOSSARY = Path(__file__).resolve().parent.parent / "docs" / "GLOSSARY.md"
SKILL_TEXTS = [Path(__file__).resolve().parent.parent / ".agents" / "skills" / "aidd" / name for name in ("SKILL.md", "references/graph.md")]
# A `term` word and the glossary term whose meaning it opens.
TERM_OF = {
    "evidence": "Evidence",
    "frozen": "Frozen test",
    "headless": "Headless run",
    "limit": "Limit",
    "method": "Method",
    "outcome": "Outcome",
    "recall": "Recall",
    "stop code": "Stop code",
    "stop rule": "Stop rule",
    "success criterion": "Success criterion",
    "work item": "Work item",
}
# Glossary terms the skill uses that `aidd explain` does not answer yet. The glossary is a page, not data the CLI ships, so
# each term needs its own entry in `term` (schemas/common.schema.json) first. The list only shrinks: the test below fails
# on a term that is missing and not listed, and on a listed term that now answers.
NOT_YET_EXPLAINABLE: set[str] = {
    "AGENTS.md",
    "Agent",
    "Author",
    "Authorization matrix",
    "Backfill Spec",
    "Blocked",
    "Branch protection",
    "Change type",
    "Comment",
    "Confidence",
    "Decision card",
    "Delegate check",
    "Delegation",
    "Development team",
    "Design files",
    "Dimension",
    "Domain pack",
    "Done when",
    "Flow",
    "Handoff note",
    "Harness",
    "Head SHA",
    "Human",
    "Hypothesis",
    "Launch",
    "Lead",
    "Local trunk",
    "Loop",
    "Observe window",
    "Owner",
    "Prototype",
    "Reaches",
    "Record",
    "Red before green",
    "Release",
    "Request",
    "Reserved action",
    "Retrospective",
    "Risk rule",
    "Scope",
    "Skill",
    "Specialist",
    "Spend cap",
    "Stack",
    "Standard",
    "Task",
    "Test runner",
    "Tests",
    "Trailer",
    "Type",
    "Work-item page",
    "aidd",
}


def glossary_rows() -> dict[str, str]:
    rows = {}
    for line in GLOSSARY.read_text(encoding="utf-8").splitlines():
        found = re.match(r"\| ([^|]+?) \| (.+) \|$", line)
        if found and found.group(1) not in ("Term", "---"):
            rows[found.group(1).strip()] = found.group(2)
    return rows


class GlossaryTermsTests(unittest.TestCase):
    def test_a_term_word_opens_the_glossarys_meaning_and_says_the_same(self):
        meanings = resources.load_json("common.schema.json")["$defs"]["term"]["x-meanings"]
        self.assertEqual(set(meanings), set(TERM_OF))
        rows = glossary_rows()
        for word, term in TERM_OF.items():
            with self.subTest(word):
                self.assertTrue(rows[term].startswith(meanings[word]), (rows[term], meanings[word]))
                found = [m for m in knowledge.explain(word) if m["type"] == "term"]
                self.assertEqual([m["what"] for m in found], [meanings[word]])

    def test_every_glossary_term_the_skill_uses_is_explainable_or_listed_as_not_yet(self):
        skill = " ".join(p.read_text(encoding="utf-8") for p in SKILL_TEXTS).lower()
        known = {knowledge.explanations.key(w) for words in knowledge.explain_words().values() for w in words}
        used = {t for t in glossary_rows() if re.search(rf"\b{re.escape(t.lower())}\b", skill)}
        explainable = {t for t in used if knowledge.explanations.key(next((w for w, n in TERM_OF.items() if n == t), t).replace("`", "")) in known}
        missing = used - explainable
        self.assertEqual(missing - NOT_YET_EXPLAINABLE, set(), "a glossary term the skill uses has no `aidd explain` answer: add it to `term`")
        self.assertEqual(NOT_YET_EXPLAINABLE - missing, set(), "these answer now: drop them from NOT_YET_EXPLAINABLE")


if __name__ == "__main__":
    unittest.main()
