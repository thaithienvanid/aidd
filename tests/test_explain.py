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
            ("spec", "lane", common["lane"]["x-meanings"]["spec"], "schemas/common.schema.json"),
            ("Specify", "loop step", "In Specify", "schemas/roles.json"),
            ("Spec approval", "decision", "what one change does", "schemas/roles.json"),
            ("verifier", "role", roles["roles"]["verifier"]["does"].split(". ")[0], "schemas/roles.json"),
            ("tech-spec", "document type", roles["loop"]["documents"]["tech-spec"]["home"], "schemas/roles.json"),
            ("In-Progress", "status", common["status"]["x-meanings"]["in_progress"], "schemas/common.schema.json"),
            ("solo", "profile", resources.load_json("profiles.json")["profiles"]["solo"]["description"], "schemas/profiles.json"),
        ]
        for word, kind, quoted, source in cases:
            found = [m for m in knowledge.explain(word) if m["kind"] == kind]
            self.assertEqual(len(found), 1, (word, kind))
            self.assertIn(quoted.rstrip("."), found[0]["what"], word)
            self.assertEqual(found[0]["source"], source, word)

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
        kinds = [m["kind"] for m in knowledge.explain("emergency")]
        self.assertEqual(kinds, ["route", "lane"])
        self.assertEqual(kinds, sorted(kinds, key=knowledge.EXPLAIN_KINDS.index))

    def test_the_schema_lists_the_kinds_in_the_order_answers_give_them(self):
        kinds = resources.load_json("explain.schema.json")["$defs"]["kind"]["enum"]
        self.assertEqual(kinds, list(knowledge.EXPLAIN_KINDS))

    def test_an_unknown_word_exits_1_and_names_the_list(self):
        with tempfile.TemporaryDirectory() as d:
            code, out = explain("flibbertigibbet", "--json", cwd=Path(d))
            self.assertEqual((code, json.loads(out)["matches"]), (1, []))
            code, out = explain("flibbertigibbet", cwd=Path(d))
        self.assertEqual(code, 1)
        self.assertIn("aidd explain --list", out)

    def test_the_list_covers_every_kind_and_validates(self):
        with tempfile.TemporaryDirectory() as d:
            code, out = explain("--list", "--json", cwd=Path(d))
        data = json.loads(out)
        self.assertEqual((code, json_schema.validate(data, "explain.schema.json")), (0, []))
        self.assertEqual(list(data["words"]), list(knowledge.EXPLAIN_KINDS))
        self.assertTrue(all(data["words"].values()), "every kind has a word")


if __name__ == "__main__":
    unittest.main()
