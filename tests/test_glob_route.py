"""A planned glob keeps its risk areas, and a path and a pattern compare in one Unicode form.

Invariant 1: the route for a glob is never lower than the route for any tracked file it matches, however many files match
and wherever the risky one sorts (R-A5). The glob stands for its files, so a cap on how many it reads would lower a route
for want of a look.

Invariant 2: a pattern and a path that differ only in Unicode normal form (NFC against NFD) match alike, with and without
case folding, because git stores the bytes it is given and macOS hands out the decomposed form (A6).

Invariant 3: `areas_in` (a whole list at once) names the same areas, with the same paths, as `areas_of` path by path.
"""

import json
import random
import unicodedata
import unittest
from unittest import mock

import helpers  # noqa: F401  (puts src on sys.path)

from aidd import config, risk
from aidd.kernel import globs

SEED = 2611
CAP = 2000  # the old limit on the files one glob stood for: the boundary rows sit around it
RISKY = "src/payments/charge.py"  # in the payments area, which routes major
HARMLESS = "src/web/page{n}.txt"


def route_of(paths, tracked=None) -> str:
    return risk.advice(None, list(paths), tracked=tracked)["route"]


def tracked_with(n: int, place: str, rng: random.Random) -> list[str]:
    """`n` harmless files and the risky one at `place`: first, last, a random place, or absent."""
    files = [HARMLESS.format(n=i) for i in range(n)]
    if place == "absent":
        return files
    at = {"first": 0, "last": n, "random": rng.randint(0, n)}[place]
    return [*files[:at], RISKY, *files[at:]]


class AGlobIsNeverLowerThanItsFilesTests(unittest.TestCase):
    def test_the_route_of_a_glob_holds_every_file_it_matches(self):
        rng = random.Random(SEED)
        for n in (0, 1, 3, CAP - 1, CAP, CAP + 1, 3 * CAP):
            for place in ("first", "last", "random", "absent"):
                tracked = tracked_with(n, place, rng)
                for glob in ("src/**", "src/", "**/*.py", "src/*/*"):
                    with self.subTest(n=n, place=place, glob=glob):
                        pattern = glob + ("**" if glob.endswith("/") else "")
                        # One file per folder stands for its folder: the fixture's files differ by folder alone.
                        by_folder = {f.rpartition("/")[0]: f for f in tracked if globs.match(pattern, f)}
                        floor = max((config.ROUTE_RANK[route_of([f])] for f in by_folder.values()), default=0)
                        self.assertGreaterEqual(config.ROUTE_RANK[route_of([glob], tracked)], floor)

    def test_the_risky_file_past_the_old_limit_still_routes_major(self):
        for place, n in (("last", CAP + 1), ("last", 3 * CAP), ("random", 3 * CAP)):
            with self.subTest(place=place, n=n):
                self.assertEqual(route_of(["src/**"], tracked_with(n, place, random.Random(SEED))), "major")

    def test_adding_files_under_a_glob_never_lowers_its_route(self):
        rng = random.Random(SEED)
        tracked = tracked_with(50, "random", rng)
        before = config.ROUTE_RANK[route_of(["src/**"], tracked)]
        for _ in range(20):
            tracked = tracked + [HARMLESS.format(n=f"x{rng.randint(0, 10**6)}")]
            self.assertGreaterEqual(config.ROUTE_RANK[route_of(["src/**"], tracked)], before)

    def test_a_reader_that_stops_at_the_old_limit_breaks_the_relation(self):
        # The relation can fail: a matcher that gives back at most CAP files reads the glob as minor.
        tracked = tracked_with(CAP + 1, "last", random.Random(SEED))
        with mock.patch.object(globs, "matching", lambda p, paths, fold_case=False: [t for t in paths if globs.match(p, t)][:CAP]):
            self.assertEqual(route_of(["src/**"], tracked), "minor")
        self.assertEqual(route_of(["src/**"], tracked), "major")


NFC = unicodedata.normalize("NFC", "café")
NFD = unicodedata.normalize("NFD", "café")


class OneUnicodeFormTests(unittest.TestCase):
    def test_a_pattern_and_a_path_match_in_either_form(self):
        self.assertNotEqual(NFC, NFD)
        for pattern in (f"src/{NFC}/**", f"src/{NFD}/**", f"**/{NFC}/*.py", f"src/{NFD}/a.py"):
            for path in (f"src/{NFC}/a.py", f"src/{NFD}/a.py"):
                for fold in (False, True):
                    with self.subTest(pattern=pattern, path=path, fold=fold):
                        self.assertTrue(globs.match(pattern, path, fold_case=fold))
                        self.assertTrue(globs.match_any([pattern], path, fold_case=fold))
                        self.assertEqual(globs.match_in([pattern], globs.keys([path], fold), fold), {0})

    def test_case_folding_holds_in_both_forms(self):
        upper = unicodedata.normalize("NFD", "CAFÉ")
        self.assertTrue(globs.match(f"src/{NFC}/**", f"src/{upper}/a.py", fold_case=True))
        self.assertFalse(globs.match(f"src/{NFC}/**", f"src/{upper}/a.py"), "without folding, case still differs")

    def test_other_names_still_differ(self):
        for other in ("cafe", "cafè", "caféx"):
            with self.subTest(other=other):
                self.assertFalse(globs.match(f"src/{NFC}/**", f"src/{other}/a.py"))

    def test_an_area_keeps_its_path_in_the_other_form(self):
        # The auditor's probe: an area `src/café/**` that routes major for the NFC path read minor for the NFD one.
        cfg = config.load_text(f'aidd_version: "1.0.0"\nprofile: team\nrisks:\n  areas:\n    cafe:\n      paths: ["src/{NFC}/**"]\n      route: major\n')
        for name in (NFC, NFD):
            with self.subTest(form="NFC" if name == NFC else "NFD"):
                self.assertEqual(risk.advice(cfg, [f"src/{name}/a.py"])["route"], "major")

    def test_overlap_and_literal_prefix_read_one_form(self):
        self.assertTrue(globs.overlap(f"src/{NFC}/**", f"src/{NFD}/a.py"))
        self.assertEqual(globs.literal_prefix(f"src/{NFD}/*"), globs.literal_prefix(f"src/{NFC}/*"))


class AreasInReadsLikeAreasOfTests(unittest.TestCase):
    PARTS = ("src", "auth", "Payments", "web", "docs", "migrations", NFC, NFD, "a.py", "x.tf", "secrets.yml", ".github")

    def test_a_list_reads_as_each_path_alone(self):
        rs = risk.rule_set(None)
        rng = random.Random(SEED)
        for _ in range(200):
            paths = ["/".join(rng.choices(self.PARTS, k=rng.randint(1, 4))) for _ in range(rng.randint(0, 12))]
            expected: dict[str, list[str]] = {}
            for p in paths:
                for a in risk.areas_of(rs, p):
                    expected.setdefault(a, []).append(p)
            got = risk.edit_level(rs, paths)[2]
            self.assertEqual(got, expected, paths)
            self.assertEqual(list(got), list(expected), "the areas come in the order their first path does")


class OneNameOneMeaningTests(unittest.TestCase):
    """`path_count` counts the planned paths in an area (`--paths`); the globs an area holds (`--list`) are `glob_count`."""

    def test_the_two_answers_name_their_counts_apart(self):
        code, out = helpers.run_cli("risk", "--list", "--json")
        self.assertEqual(code, 0, out)
        areas = json.loads(out)["areas"]
        self.assertTrue(areas and all(set(a) == {"glob_count", "route"} for a in areas.values()), areas)
        code, out = helpers.run_cli("risk", "--paths", "src/payments/charge.py", "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual({a["path_count"] for a in json.loads(out)["areas"]}, {1})


if __name__ == "__main__":
    unittest.main()
