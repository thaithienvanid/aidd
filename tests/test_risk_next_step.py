"""`aidd risk --paths` gives one next step: a new feature with no test gets its test first inside the step of a change with no
Spec, never a second step that names another route, and the step of a change with a Spec names the command as it runs."""

import contextlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import make_repo, run_cli

from aidd import config, risk


class OneNextStepTests(unittest.TestCase):
    def test_one_step_by_the_route_and_whether_the_new_code_has_a_test(self):
        cases = [
            # (planned paths, tracked files, the change type, the route, whether the step writes the new code's test first)
            (["src/orders.py"], [], "feat", "minor", True),
            (["src/orders.py", "tests/test_orders.py"], [], "feat", "minor", False),
            (["src/orders.py"], ["src/orders.py"], "feat", "minor", False),
            (["src/orders.py"], [], "fix", "minor", False),
            (["src/payments/charge.py"], [], "feat", "major", False),
        ]
        for paths, tracked, change_type, route, test_first in cases:
            answer = risk.advice(None, paths, change_type=change_type, tracked=tracked)
            self.assertEqual((answer["route"], answer["hints"]), (route, []), paths)
            self.assertEqual("write a test for the new code" in answer["next"]["what"].casefold(), test_first, (paths, answer["next"]["what"]))
            self.assertNotIn("<ID>", answer["next"]["what"], "`aidd new spec` picks the id itself")

    def test_the_text_has_one_next_line_and_no_hint(self):
        # Inside a repository, as an agent runs it: outside one, aidd adds a true hint that a glob names no tracked file.
        with tempfile.TemporaryDirectory() as d, contextlib.chdir(d):
            subprocess.run(["git", "init", "-q"], check=True, stdin=subprocess.DEVNULL)
            code, out = run_cli("risk", "--paths", "src/orders.py")
        self.assertEqual(code, 0, out)
        self.assertEqual(sum(line.startswith("next:") for line in out.splitlines()), 1, out)
        self.assertFalse([line for line in out.splitlines() if line.startswith("hint:")], out)


if __name__ == "__main__":
    unittest.main()


class FromASubfolderTests(unittest.TestCase):
    """A relative path typed in a subfolder is read from there, as git reads it, never from the repository's top: from
    src/billing/, `charge.py` is a billing file, which the built-in payments area routes major."""

    def test_a_relative_path_is_read_from_the_folder_it_was_typed_in(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d) / "shop", branch=None)
            (root / "src" / "billing").mkdir(parents=True)
            with contextlib.chdir(root / "src" / "billing"):
                code, out = run_cli("risk", "--paths", "charge.py", "--json")
            self.assertEqual(code, 0, out)
            answer = json.loads(out)
            self.assertEqual(answer["route"], "major", answer)
            self.assertIn("payments", [a["area"] for a in answer["areas"]])


BASE = 'aidd_version: "1.0.0"\nprofile: solo\n'
LIST = "agents:\n  domain_skills:\n"
SIGN_IN = "risks:\n  areas:\n    sign_in: {paths: ['partners/**'], route: normal}\n"
PAYMENTS = {"name": "payments-and-finance", "because": "payments"}
INSURANCE = {"name": "insurance", "because": "project"}


def skills_of(extra: str, paths: list[str]) -> list[dict]:
    """The domain skills `aidd risk --paths` names for `paths` in a project whose config is `BASE + extra`."""
    return risk.advice(config.load_text(BASE + extra), paths)["skills"]


class DomainSkillsTests(unittest.TestCase):
    """A path calls for a domain skill in exactly two ways: an area it matches is one of the skill's `areas`, or the project's
    list holds the skill with no `when_changed`, or with a glob that matches."""

    def test_the_skills_a_path_calls_for(self):
        cases = {
            "a built-in area whose skill has that area": ("", ["src/payments/charge.py"], [PAYMENTS]),
            "the infra area, which cloud-and-infrastructure has": ("", ["infra/main.tf"], [{"name": "cloud-and-infrastructure", "because": "infra"}]),
            "no area and no list": ("", ["README.md"], []),
            "no path": ("", [], []),
            "a path in no area, a skill in the list with no glob": (LIST + "    - insurance\n", ["README.md"], [INSURANCE]),
            "the list in flow form": ("agents:\n  domain_skills: [insurance]\n", ["README.md"], [INSURANCE]),
            "an empty list": ("agents:\n  domain_skills: []\n", ["README.md"], []),
            "a glob that matches": (LIST + "    - {name: insurance, when_changed: ['claims/**']}\n", ["claims/rule.py"], [INSURANCE]),
            "a glob that does not match": (LIST + "    - {name: insurance, when_changed: ['claims/**']}\n", ["README.md"], []),
            "one of two planned paths matches the glob": (
                LIST + "    - {name: insurance, when_changed: ['claims/**']}\n",
                ["README.md", "claims/rule.py"],
                [INSURANCE],
            ),
            "the second of two globs matches": (
                LIST + "    - {name: insurance, when_changed: ['policies/**', 'claims/**']}\n",
                ["claims/rule.py"],
                [INSURANCE],
            ),
            "a folder as a planned path stands for the files in it": (
                LIST + "    - {name: insurance, when_changed: ['claims/**']}\n",
                ["claims/"],
                [INSURANCE],
            ),
            "named by an area and by the list: once, with the area": (LIST + "    - payments-and-finance\n", ["src/payments/charge.py"], [PAYMENTS]),
            "named by an area and by a glob that does not match: once, with the area": (
                LIST + "    - {name: payments-and-finance, when_changed: ['nothing/**']}\n",
                ["src/payments/charge.py"],
                [PAYMENTS],
            ),
            "listed twice, once with a glob that does not match: named by the entry with none": (
                LIST + "    - {name: insurance, when_changed: ['nothing/**']}\n    - insurance\n",
                ["README.md"],
                [INSURANCE],
            ),
            "an area name that is the project's own": (SIGN_IN, ["partners/desk.py"], [{"name": "enterprise-controls", "because": "sign_in"}]),
            "that area name where the project defines no such area": ("", ["partners/desk.py"], []),
            "an area and the list call for two skills: in name order": (
                LIST + "    - apis-and-services\n",
                ["src/payments/charge.py"],
                [{"name": "apis-and-services", "because": "project"}, PAYMENTS],
            ),
        }
        for name, (extra, paths, want) in cases.items():
            with self.subTest(name):
                self.assertEqual(skills_of(extra, paths), want)

    def test_no_config_names_a_skill_by_its_areas_alone(self):
        self.assertEqual(risk.advice(None, ["src/payments/charge.py"])["skills"], [PAYMENTS])

    def test_a_config_built_in_code_reads_an_empty_glob_list_as_matching_nothing(self):
        """The schema refuses `when_changed: []`, but a `Config` made in code is not validated: an entry that can never match names no skill."""
        cases = {
            "no `when_changed`: every change": ({"name": "insurance"}, [INSURANCE]),
            "an empty `when_changed`: no change": ({"name": "insurance", "when_changed": []}, []),
            "a glob that matches": ({"name": "insurance", "when_changed": ["README.*"]}, [INSURANCE]),
        }
        for name, (entry, want) in cases.items():
            with self.subTest(name):
                cfg = config.Config({"agents": {"domain_skills": [entry]}}, "solo")
                self.assertEqual(risk.advice(cfg, ["README.md"])["skills"], want)

    def test_the_reason_is_the_first_area_the_answer_lists(self):
        """`enterprise-controls` has the `auth` and `sign_in` areas, so a change in both says the one that comes first."""
        for paths in (["src/auth/token.py", "partners/desk.py"], ["partners/desk.py", "src/auth/token.py"]):
            with self.subTest(paths):
                answer = risk.advice(config.load_text(BASE + SIGN_IN), paths)
                first = next(a["area"] for a in answer["areas"] if a["area"] in ("auth", "sign_in"))
                self.assertEqual([s for s in answer["skills"] if s["name"] == "enterprise-controls"], [{"name": "enterprise-controls", "because": first}])


ROUTE_ANSWERS = Path(__file__).parent / "fixtures" / "risk" / "route_answers.json"


class SkillsLeaveTheRouteAloneTests(unittest.TestCase):
    """Naming the domain skills is the only change to the answer: over a generated set of path lists (a path of each built-in area, a
    pair of areas, and paths in none), the route, its reasons, the edit level, the Spec approval, the specialists, and the next step
    are what `tests/fixtures/risk/route_answers.json` holds. It was recorded from `risk.advice` before it named any skill."""

    def cases(self) -> list[dict]:
        return json.loads(ROUTE_ANSWERS.read_text(encoding="utf-8"))["cases"]

    def test_the_answer_without_its_skills_is_the_recorded_one(self):
        configs = {"none": None, "list": config.load_text(BASE + LIST + "    - insurance\n")}
        for case in self.cases():
            with self.subTest(case["config"], paths=case["paths"]):
                answer = risk.advice(configs[case["config"]], case["paths"])
                self.assertIsInstance(answer.pop("skills"), list)
                self.assertEqual(answer, case["answer"])

    def test_the_recorded_set_reaches_every_built_in_area_and_both_configs(self):
        cases = self.cases()
        self.assertEqual({c["config"] for c in cases}, {"none", "list"})
        reached = {a["area"] for c in cases for a in c["answer"]["areas"]}
        self.assertEqual(reached, set(risk.builtin()["areas"]))
        self.assertGreater(len({c["answer"]["route"] for c in cases}), 1, "the set holds more than one route")


class DomainSkillsAnswerTests(unittest.TestCase):
    """The JSON holds `skills`, the text prints one `read:` line for each, and `hints` carries no skill to load."""

    def answer(self, extra: str, *paths: str) -> tuple[dict, list[str]]:
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d) / "shop", branch=None)
            cfg = root / ".aidd" / "config.yaml"
            cfg.write_text(cfg.read_text(encoding="utf-8") + extra, encoding="utf-8")
            with contextlib.chdir(root):
                code, text = run_cli("risk", "--paths", *paths)
                self.assertEqual(code, 0, text)
                code, out = run_cli("risk", "--paths", *paths, "--json")
                self.assertEqual(code, 0, out)
        return json.loads(out), text.splitlines()

    def test_the_text_names_each_skill_with_its_reason(self):
        answer, lines = self.answer(LIST + "    - insurance\n", "src/payments/charge.py")
        self.assertEqual(answer["skills"], [INSURANCE, PAYMENTS])
        self.assertEqual(
            [line for line in lines if line.startswith("read:")],
            [
                "read: aidd-domains:insurance (domain skill, this project's list)",
                "read: aidd-domains:payments-and-finance (domain skill, the payments area)",
            ],
        )
        self.assertEqual([h for h in answer["hints"] if "domain skill" in h], [])

    def test_a_path_that_calls_for_no_skill_has_no_read_line_and_an_empty_list(self):
        answer, lines = self.answer("", "README.md")
        self.assertEqual(answer["skills"], [])
        self.assertEqual([line for line in lines if line.startswith("read:")], [])
