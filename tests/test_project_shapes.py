"""The project-shape matrix: every eval case and core fixture names the project shape it shows, and the table shows the
pairs no case covers. evals/shapes.json holds the axes, and src/aidd/evals/shapes.py reads them."""

import json
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd import evals
from aidd.evals import claims
from aidd.evals import shapes as shapes_module


class ShapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.file = evals.shapes_file(ROOT)
        cls.rows = evals.case_shapes(ROOT)

    def test_every_case_names_one_project_shape_of_the_axes(self):
        self.assertEqual(evals.shape_problems(self.rows, self.file), [])
        self.assertEqual(len(self.rows), len(evals.suite_cases(ROOT)), "a project shape for each case the claims table counts")

    def test_every_core_fixture_names_a_project_shape_or_shows_no_project(self):
        self.assertEqual(evals.fixture_problems(ROOT, self.file), [])

    def test_the_axes_are_the_four_and_any_is_only_a_type(self):
        axes = self.file["axes"]
        self.assertEqual(tuple(axes), ("type", "stage", "team", "regulation"))
        self.assertEqual(list(axes["type"])[-1], "any", "`any` is last, after every real type")
        for axis in ("stage", "team", "regulation"):
            self.assertNotIn("any", axes[axis], "a case always knows its stage, team, and regulation")

    def test_the_types_follow_the_packs(self):
        """Each type names the packs that hold its knowledge, and each technology pack is a type's or a concern of every type."""
        packs = {p["slug"]: p["type"] for p in json.loads((ROOT / "schemas" / "packs.json").read_text(encoding="utf-8"))}
        named = [slug for value in self.file["axes"]["type"].values() for slug in value["packs"]]
        self.assertLessEqual(set(named) | set(self.file["concerns"]), set(packs), "a type or a concern names a pack that does not exist")
        self.assertEqual(len(named), len(set(named)), "a pack belongs to one type")
        self.assertFalse(set(named) & set(self.file["concerns"]), "a pack is a type's or a concern, never both")
        technology = {slug for slug, kind in packs.items() if kind == "technology"}
        self.assertEqual(sorted(technology - set(named) - set(self.file["concerns"])), [], "a technology pack the type axis does not follow")
        for value in self.file["axes"]["type"].values():
            self.assertTrue(value["means"].strip())

    def test_a_team_value_is_a_profile(self):
        profiles = json.loads((ROOT / "schemas" / "profiles.json").read_text(encoding="utf-8"))["profiles"]
        team = self.file["axes"]["team"]
        self.assertEqual({v["profile"] for v in team.values()}, set(profiles))
        self.assertTrue(all(set(v) == {"profile"} for v in team.values()), "the profile says what a team value means")

    def test_the_checker_names_each_defect(self):
        good = "web-app/brownfield/team/unregulated"
        cases = {
            "a good shape": (good, None),
            "a type of any": ("any/greenfield/solo/regulated", None),
            "no shape": ("", "name its `shape`"),
            "two shapes": (f"{good} cli/brownfield/team/unregulated", "it names 2 shapes"),
            "three parts": ("web-app/brownfield/team", "name it as type/stage/team/regulation"),
            "the axes out of order": ("brownfield/web-app/team/unregulated", "its type is one of"),
            "an unknown type": ("spaceship/brownfield/team/unregulated", "its type is one of"),
            "any as a stage": ("web-app/any/team/unregulated", "its stage is one of"),
            "an unknown team": ("web-app/brownfield/company/unregulated", "its team is one of"),
        }
        for label, (shape, message) in cases.items():
            with self.subTest(label):
                problems = evals.shape_problems([{"suite": "routing", "id": "c1", "shape": shape}], self.file)
                self.assertEqual(len(problems), 0 if message is None else 1, problems)
                if message:
                    self.assertIn(message, problems[0])

    def test_a_fixture_with_no_project_shape_and_a_listed_path_that_is_gone_are_problems(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tests" / "fixtures" / "specs").mkdir(parents=True)
            (root / "tests" / "fixtures" / "junit").mkdir()
            (root / "tests" / "fixtures" / "specs" / "SPEC-1.md").write_text("x", encoding="utf-8")
            (root / "tests" / "fixtures" / "specs" / "SPEC-2.md").write_text("x", encoding="utf-8")
            (root / "tests" / "fixtures" / "junit" / "passed.xml").write_text("x", encoding="utf-8")
            file = dict(
                self.file,
                fixtures={
                    "tests/fixtures/specs/SPEC-1.md": "cli/greenfield/solo/unregulated",
                    "tests/fixtures/specs/SPEC-9.md": "cli/greenfield/solo/unregulated",
                },
                not_project_shaped={"tests/fixtures/junit": "reports"},
            )
            problems = evals.fixture_problems(root, file)
        self.assertEqual(len(problems), 2, problems)
        self.assertTrue(problems[0].startswith("tests/fixtures/specs/SPEC-9.md: listed"), problems)
        self.assertTrue(problems[1].startswith("tests/fixtures/specs/SPEC-2.md: name its project shape"), problems)

    def test_a_trigger_case_takes_its_shape_from_triggers_json(self):
        triggers = json.loads((ROOT / claims.SUITES["team"] / "triggers.json").read_text(encoding="utf-8"))
        names = {c["name"]: c["shape"] for entry in triggers["skills"].values() for c in entry["cases"]}
        shapes = {r["id"]: r["shape"] for r in self.rows if r["suite"] == "team"}
        for name, shape in names.items():
            with self.subTest(name):
                self.assertEqual(shapes[name], shape)
                prompt = ROOT / claims.SUITES["team"] / name / "prompt.md"
                if prompt.is_file():  # a written case: the generated files leave the shape out
                    self.assertNotIn("shape:", prompt.read_text(encoding="utf-8"))

    def test_the_table_counts_the_cases_of_each_pair_and_names_the_empty_ones(self):
        rows = [
            {"suite": "routing", "id": "a", "shape": "web-app/brownfield/team/unregulated"},
            {"suite": "routing", "id": "b", "shape": "web-app/greenfield/team/regulated"},
            {"suite": "routing", "id": "c", "shape": "any/brownfield/solo/unregulated"},
        ]
        table = evals.shape_coverage_table(rows, dict(self.file, fixtures={})).splitlines()
        types = len(self.file["axes"]["type"])
        self.assertEqual(table[0], "| Type | Cases | Fixtures | greenfield | brownfield | solo | team | regulated | unregulated |")
        self.assertIn("| `web-app` | 2 | 0 | 1 | 1 | 0 | 2 | 1 | 1 |", table)
        self.assertIn("| `any` | 1 | 0 | 0 | 1 | 1 | 0 | 0 | 1 |", table)
        empty = table[2 + types :]
        self.assertIn("- `web-app`: solo", empty)
        self.assertIn("- `cli`: greenfield, brownfield, solo, team, regulated, unregulated", empty)
        self.assertFalse([line for line in empty if line.startswith("- `any`")], "`any` is no type, so it has no empty pair")
        self.assertEqual(shapes_module.empty_pairs([r["shape"] for r in rows], self.file)["web-app"], ["solo"])

    def test_a_fixture_counts_in_its_own_column_and_fills_no_pair(self):
        file = dict(self.file, fixtures={"f": "cli/greenfield/solo/regulated"})
        table = evals.shape_coverage_table([], file).splitlines()
        self.assertIn("| `cli` | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |", table)
        self.assertIn("- `cli`: greenfield, brownfield, solo, team, regulated, unregulated", table)

    def test_the_stage_and_type_columns_add_up_to_the_cases(self):
        table = evals.shape_coverage_table(self.rows, self.file).splitlines()
        for line in table[2 : 2 + len(self.file["axes"]["type"])]:
            cells = [c.strip() for c in line.strip("|").split("|")]
            with self.subTest(cells[0]):
                self.assertEqual(int(cells[3]) + int(cells[4]), int(cells[1]), "greenfield and brownfield split the cases")

    def test_with_every_pair_covered_the_table_says_so(self):
        values = [list(self.file["axes"][axis]) for axis in ("stage", "team", "regulation")]
        shapes = [f"{kind}/{values[0][n % 2]}/{values[1][n % 2]}/{values[2][n % 2]}" for kind in self.file["axes"]["type"] for n in range(2)]
        rows = [{"suite": "routing", "id": str(n), "shape": shape} for n, shape in enumerate(shapes)]
        self.assertEqual(shapes_module.empty_pairs(shapes, self.file), {})
        self.assertEqual(evals.shape_coverage_table(rows, dict(self.file, fixtures={})).splitlines()[-1], "No pair is empty.")


if __name__ == "__main__":
    unittest.main()
