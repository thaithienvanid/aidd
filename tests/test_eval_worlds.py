"""The worlds an eval case's project is set in: evals/worlds.json lists them, each seed builds a project aidd accepts, a live case
names one, and no one world, language, or domain holds more than `cap` of the live cases. No test here starts a model."""

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from eval_fixture_repos import build, language_problem, languages_held, live_worlds
from helpers import ROOT, aidd_here

from aidd import evals
from aidd.evals import claims, worlds
from aidd.kernel import json_schema

FILE = evals.worlds_file(ROOT)
LIVE = evals.case_worlds(ROOT)


def rows(**counts: int) -> list[dict]:
    """Live cases: `counts` is the number set in each world."""
    return [{"suite": "team", "id": f"{world}-{n}", "worlds": [world]} for world, count in counts.items() for n in range(count)]


class FileTests(unittest.TestCase):
    def test_the_file_follows_its_schema(self):
        self.assertEqual(json_schema.validate(FILE, "eval-worlds.schema.json"), [])

    def test_the_languages_and_the_worlds_are_in_their_stated_order(self):
        languages = list(FILE["languages"])
        self.assertEqual(languages[-1], worlds.NO_LANGUAGE, "`none` is last")
        self.assertEqual(languages[:-1], sorted(languages[:-1]))
        names = list(FILE["worlds"])
        key = lambda name: (languages.index(FILE["worlds"][name]["language"]), FILE["worlds"][name]["domain"])  # noqa: E731
        self.assertEqual(names, sorted(names, key=key), "worlds follow the languages, then the domains")

    def test_every_world_is_named_by_its_language_and_domain_and_has_a_seed(self):
        self.assertEqual(worlds.definition_problems(ROOT, FILE), [])

    def test_every_live_case_names_one_world_and_no_share_is_over_the_cap(self):
        self.assertEqual(worlds.world_problems(ROOT, LIVE, FILE), [])
        self.assertTrue(LIVE and all(worlds.one_world(r) in FILE["worlds"] for r in LIVE))

    def test_a_live_case_is_one_that_builds_its_own_project_and_no_trigger_case_is(self):
        ids = {f"{r['suite']}/{r['id']}" for r in LIVE}
        for suite in ("plugin", "team"):
            folders = {
                f"{suite}/{p.parent.name}"
                for p in (ROOT / "evals" / suite).glob("*/fixture.sh")
                if not p.parent.name.startswith(("loads-", "skips-", "held-out-"))
            }
            self.assertEqual({i for i in ids if i.startswith(f"{suite}/")}, folders)
        self.assertEqual(len(live_worlds()), len(LIVE))

    def test_a_case_that_builds_no_project_names_no_world(self):
        """The routing, roles, and trigger cases carry no `world:` tag, so a tag there would count a project that is never built."""
        for row in claims.suite_cases(ROOT):
            if (row["suite"], row["id"]) not in {(r["suite"], r["id"]) for r in LIVE}:
                self.assertFalse([t for t in row["tags"] if t.startswith("world:")], f"{row['suite']}/{row['id']}")

    def test_the_over_cap_rows_are_the_shares_over_the_cap(self):
        total = len(LIVE)
        for axis, listed in FILE["over_cap"].items():
            over = {value: n for value, n in worlds.share_counts(LIVE, FILE)[axis].items() if n > FILE["cap"] * total}
            self.assertEqual(over, listed, axis)


class SeedTests(unittest.TestCase):
    """Each world's seed builds with no model, and aidd gives the stated answers in it."""

    def test_each_seed_builds_a_project_of_its_language_that_aidd_accepts_and_routes_as_stated(self):
        for name, world in FILE["worlds"].items():
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp)
                build(ROOT / world["seed"], work)
                with mock.patch.dict(os.environ, {"HOME": tmp, "AIDD_OFFLINE": "1"}):
                    checked = aidd_here("validate", cwd=work)
                    self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
                    for row in world["risk"]:
                        said = aidd_here("risk", "--paths", *row["paths"], "--json", cwd=work)
                        self.assertEqual(said.returncode, 0, said.stdout + said.stderr)
                        self.assertEqual(json.loads(said.stdout)["route"], row["route"], f"{name}: {row['paths']}")
                self.assertIsNone(language_problem(f"world/{name}", name, languages_held(work, FILE), FILE))
                self.assertIn("profile: solo", (work / ".aidd" / "config.yaml").read_text(encoding="utf-8"))

    def test_the_worlds_differ_in_what_they_show(self):
        """Two worlds that share a language and a domain would be one world twice, and a language alone would hide a domain."""
        self.assertEqual(len({(w["language"], w["domain"]) for w in FILE["worlds"].values()}), len(FILE["worlds"]))
        self.assertGreaterEqual(len({w["language"] for w in FILE["worlds"].values()} - {worlds.NO_LANGUAGE}), 5)
        self.assertGreaterEqual(len({w["domain"] for w in FILE["worlds"].values()} - {worlds.NO_DOMAIN}), 5)


class LanguageTests(unittest.TestCase):
    def held(self, *files: str) -> set[str]:
        with tempfile.TemporaryDirectory() as tmp:
            for rel in files:
                path = Path(tmp) / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("x", encoding="utf-8")
            return languages_held(Path(tmp), FILE)

    def test_a_language_shows_by_a_suffix_or_a_file_name_and_markup_and_shell_show_none(self):
        cases = {
            "nothing": ([], set()),
            "a Python file": (["src/a.py"], {"python"}),
            "a package.json alone": (["package.json"], {"javascript"}),
            "a Go module name alone": (["go.mod"], {"go"}),
            "two languages": (["a.py", "b.rs"], {"python", "rust"}),
            "a page, a style, a script, and a doc": (["a.html", "b.css", "c.sh", "d.md"], set()),
            "a name that only ends like a marker": (["notgo.mod", "x.pyc"], set()),
            "files under a folder that starts with a dot": ([".claude/hook.mjs", ".git/x.py"], set()),
            "files in a bare repository": (["remote.git/hooks/update.py"], set()),
            "a stand-in program in bin": (["bin/tool.py"], set()),
            "a bin deeper in the project is the project's": (["src/bin/tool.py"], {"python"}),
        }
        for name, (files, want) in cases.items():
            with self.subTest(name):
                self.assertEqual(self.held(*files), want)

    def test_a_case_that_names_the_wrong_world_is_a_problem(self):
        cases = {
            "the language held": ("python-notes", {"python"}, False),
            "another language held": ("go-logistics", {"python"}, True),
            "two languages for one": ("python-notes", {"python", "rust"}, True),
            "no source for a language": ("python-notes", set(), True),
            "no source for none": ("none-general", set(), False),
            "a language for none": ("none-general", {"python"}, True),
        }
        for name, (world, held, problem) in cases.items():
            with self.subTest(name):
                got = language_problem("team/x", world, held, FILE)
                self.assertEqual(got is not None, problem, got)


class CheckerTests(unittest.TestCase):
    def test_a_world_that_is_misnamed_or_names_a_language_the_file_lacks_or_has_no_seed(self):
        cases = {
            "as shipped": (lambda f: None, 0),
            "a name that is not its language and domain": (lambda f: f["worlds"].update({"python-shop": f["worlds"].pop("python-commerce")}), 1),
            "an unknown language": (lambda f: f["worlds"]["python-notes"].update(language="cobol"), 2),
            "a seed that is no file": (lambda f: f["worlds"]["python-notes"].update(seed="evals/worlds/nowhere/world.sh"), 1),
        }
        for name, (edit, count) in cases.items():
            with self.subTest(name):
                file = copy.deepcopy(FILE)
                edit(file)
                self.assertEqual(len(worlds.definition_problems(ROOT, file)), count, worlds.definition_problems(ROOT, file))

    def test_a_case_that_names_no_world_two_or_an_unknown_one_is_a_problem(self):
        good = {"suite": "team", "id": "a", "worlds": ["python-notes"]}
        cases = {
            "one world": (good, 0),
            "none": (dict(good, worlds=[]), 1),
            "two": (dict(good, worlds=["python-notes", "go-logistics"]), 1),
            "an unknown one": (dict(good, worlds=["cobol-banking"]), 1),
        }
        for name, (row, count) in cases.items():
            with self.subTest(name):
                self.assertEqual(len(worlds.naming_problems([row], FILE)), count)

    def test_a_share_over_the_cap_is_a_problem_unless_over_cap_lists_it_at_its_count(self):
        """Ten live cases and a cap of 40%: four cases are at the cap and five are over it. python-notes puts the world, the language,
        and the domain over together, so each axis names it once. A listed count must be the real one, and it goes when under the cap."""

        def problems(live: list[dict], world: int = 0, language: int = 0, domain: int = 0) -> list[str]:
            listed = {"world": {"python-notes": world}, "language": {"python": language}, "domain": {"notes": domain}}
            file = dict(copy.deepcopy(FILE), cap=0.4, over_cap={axis: {k: n for k, n in v.items() if n} for axis, v in listed.items()})
            return worlds.share_problems(live, file)

        at_cap = rows(**{"python-notes": 4, "go-logistics": 3, "rust-general": 3})
        over = rows(**{"python-notes": 5, "go-logistics": 3, "rust-general": 2})
        grown = rows(**{"python-notes": 6, "go-logistics": 2, "rust-general": 2})
        cases = {
            "at the cap": (problems(at_cap), []),
            "over the cap and unlisted": (problems(over), ["world", "language", "domain"]),
            "over the cap and listed at its count": (problems(over, 5, 5, 5), []),
            "one count that fell": (problems(over, 5, 6, 5), ["language"]),
            "a listed row under the cap": (problems(at_cap, 0, 5, 0), ["language"]),
            "a share that grew past its listed count": (problems(grown, 5, 5, 5), ["world", "language", "domain"]),
            "no live case": (problems([], 0, 0, 0), []),
        }
        for name, (got, axes) in cases.items():
            with self.subTest(name):
                self.assertEqual([p.split(" ", 1)[0] for p in got], axes, got)

    def test_a_count_that_rose_is_told_to_move_cases_and_one_that_fell_to_lower_the_record(self):
        """A count may only fall, so no message tells an author to raise it: a rise or a new share asks for cases to move, and a fall
        asks for the one edit `over_cap` takes."""
        file = dict(copy.deepcopy(FILE), cap=0.4)

        def said(live: list[dict], listed: int) -> str:
            file["over_cap"] = {"world": {"python-notes": listed} if listed else {}, "language": {}, "domain": {}}
            return next(p for p in worlds.share_problems(live, file) if p.startswith("world "))

        # Ten cases over python-notes 5, go-logistics 3, rust-general 2 put python-notes at 5, over the cap of 4.
        over = rows(**{"python-notes": 5, "go-logistics": 3, "rust-general": 2})
        cases = {
            "a new share over the cap": (said(over, 0), "move cases", "lower"),
            "a count that rose": (said(over, 4), "move cases", "lower"),
            "a count that fell": (said(over, 6), "lower the count to 5", "move cases"),
        }
        for name, (message, wants, never) in cases.items():
            with self.subTest(name):
                self.assertIn(wants, message)
                self.assertNotIn(never, message)
                self.assertNotIn("raise", message)

    def test_the_cap_holds_for_the_language_none_and_the_domain_general_like_any_other(self):
        """Ten live cases in `none-general` are ten in the world, ten in the language `none`, and ten in the domain `general`, so each is
        over a cap of 40% unless `over_cap` lists it. A domain is `general` in more than one world, so those worlds' cases add up."""
        file = copy.deepcopy(FILE)
        file["over_cap"] = {"world": {}, "language": {}, "domain": {}}
        counts = worlds.share_counts(rows(**{"none-general": 10}), file)
        self.assertEqual({axis: dict(c) for axis, c in counts.items()}, {"world": {"none-general": 10}, "language": {"none": 10}, "domain": {"general": 10}})
        self.assertEqual([p.split(" ", 1)[0] for p in worlds.share_problems(rows(**{"none-general": 10}), file)], ["world", "language", "domain"])
        file["over_cap"] = {"world": {"none-general": 10}, "language": {"none": 10}, "domain": {"general": 10}}
        self.assertEqual(worlds.share_problems(rows(**{"none-general": 10}), file), [])
        mixed = worlds.share_counts(rows(**{"python-general": 3, "rust-general": 1, "none-general": 2}), file)
        self.assertEqual(dict(mixed["domain"]), {"general": 6})
        self.assertEqual(dict(mixed["language"]), {"python": 3, "rust": 1, "none": 2})

    def test_the_table_lists_each_world_with_its_share_and_each_share_over_the_cap(self):
        live = rows(**{"python-notes": 6, "go-logistics": 4})
        file = dict(copy.deepcopy(FILE), cap=0.5)
        table = worlds.world_coverage_table(live, file).splitlines()
        self.assertEqual(table[0], "| World | Language | Domain | Live cases | Share |")
        self.assertIn("| `python-notes` | python | notes | 6 | 60.0% |", table)
        self.assertIn("| `go-logistics` | go | logistics | 4 | 40.0% |", table)
        self.assertIn("- `python-notes` (world): 6 of 10 live cases, 60.0%", table)
        self.assertIn("- `python` (language): 6 of 10 live cases, 60.0%", table)
        none_over = worlds.world_coverage_table(rows(**{"python-notes": 5, "go-logistics": 5}), file).splitlines()
        self.assertEqual(none_over[-1], "No world, language, or domain is over the cap of 50%.")
        just_over = worlds.world_coverage_table(rows(**{"python-notes": 29, "go-logistics": 43}), dict(copy.deepcopy(FILE), cap=0.4)).splitlines()
        self.assertIn("- `python-notes` (world): 29 of 72 live cases, 40.3%", just_over, "a share just over the cap is not shown as the cap")


if __name__ == "__main__":
    unittest.main()
