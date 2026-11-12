"""The answer of `aidd risk --paths` lists at most `limits.max_paths_shown` paths of an area, and the cap decides nothing. For every area
size, the route, the edit level, and the scope of a new Spec come from every path, and the answer says how many it left out."""

import json
import re
import unittest

from helpers import adopted_repo, aidd_here, git

from aidd import config, risk
from aidd.cli.commands import risk_answers
from aidd.kernel import resources

CAP = config.EMPTY.max_paths_shown


def advice_with(count: int) -> dict:
    """What `risk.advice` gives for `count` paths in one area, as the data the cap reads."""
    paths = [f"src/auth/f{i:03}.py" for i in range(count)]
    return {"areas": [{"area": "auth", "paths": paths}] if count else [], "hints": ["kept"], "route": "major", "edit": {"level": "ask"}}


class CapAreaPaths(unittest.TestCase):
    def test_every_area_size_keeps_its_count_and_names_what_it_left_out(self):
        """Table: none, one, below the cap, the cap, one past it, and many."""
        for count in (0, 1, CAP - 1, CAP, CAP + 1, 10 * CAP):
            with self.subTest(count=count):
                answer = advice_with(count)
                shown = risk_answers.cap_area_paths(answer, CAP)
                listed = [hit for hit in shown["areas"]]
                self.assertEqual([len(hit["paths"]) for hit in listed], [min(count, CAP)] if count else [])
                self.assertEqual([hit["path_count"] for hit in listed], [count] if count else [])
                self.assertEqual(shown["route"], answer["route"], "the cap changes no decision")
                self.assertEqual(shown["edit"], answer["edit"])
                left = [h for h in shown["hints"] if "leaves out" in h]
                self.assertEqual(len(left), 1 if count > CAP else 0, shown["hints"])
                if count > CAP:
                    self.assertIn(f"auth ({count - CAP} of {count})", left[0])
                self.assertEqual(shown["hints"][0], "kept")
                self.assertEqual(len(answer["areas"][0]["paths"]) if count else 0, count, "the answer it reads is not changed")

    def test_the_schema_says_the_same_number_as_the_code(self):
        schema = resources.load_json("risk.schema.json")["$defs"]["paths"]["properties"]["areas"]["items"]["properties"]
        self.assertEqual(re.search(r"at most (\d+)", schema["paths"]["description"]).group(1), str(config.setting_default("limits.max_paths_shown")))
        self.assertIn("path_count", schema)


class TheCapDecidesNothing(unittest.TestCase):
    """The scope of a new Spec keeps each file an area matched exact: a file listed past the cap is not widened to its folder."""

    def test_a_new_spec_names_every_file_of_an_area_past_the_cap(self):
        files = [f"src/auth/f{i:03}.py" for i in range(CAP + 1)]
        with adopted_repo("solo", branch=None) as root:
            (root / "src" / "auth").mkdir(parents=True)
            for rel in files:
                (root / rel).write_text("x = 1\n", encoding="utf-8")
            git(root, "add", "-A")
            git(root, "commit", "-q", "-m", "files")
            run = aidd_here("risk", "--paths", *files, "--json", cwd=root)
            data = json.loads(run.stdout)
            hit = next(a for a in data["areas"] if a["area"] == "auth")
            self.assertEqual((len(hit["paths"]), hit["path_count"]), (CAP, CAP + 1), "the answer is capped and says how many matched")
            self.assertEqual(data["route"], risk.advice(None, files, tracked=files)["route"], "the route comes from every path")
            made = aidd_here("new", "spec", "Tighten auth", "--paths", *files, cwd=root)
            self.assertEqual(made.returncode, 0, made.stderr)
            spec = next((root / "specs").glob("SPEC-*.md")).read_text(encoding="utf-8")
            for rel in files:
                self.assertIn(rel, spec, "each file stays exact in the scope, past the cap too")
            self.assertNotIn("src/auth/\n", spec.split("scope:")[1].split("tests:")[0], "no file was widened to its folder")


if __name__ == "__main__":
    unittest.main()
