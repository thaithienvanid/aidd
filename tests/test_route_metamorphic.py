"""Metamorphic tests on the route: a change to a project that does not change its risk never changes its route.

A unit test checks one path's route against a label. These check a relation between two inputs instead, so they need no label and
hold for paths nobody wrote a case for (CONTRIBUTING.md, "Keep aidd generic", step 5):

- renaming the project, or swapping its stack, never changes a route: not in the config, and not in a folder;
- a file of any area takes the same route in another language, except a tool's own file name (TOOL_FILES) and the gaps
  KNOWN_LANGUAGE_GAPS names, which only shrinks;
- the order of the paths, or a path named twice, never changes a route;
- adding a file in no area never changes a route;
- adding paths never lowers a route, so a risky path in a change always counts (monotonic risk);
- the change type never changes a route, and a declared risk dimension raises it to the dimension's floor and never lowers it.

The inputs come from the built-in areas' own patterns and from neutral words, with a fixed seed and a bounded count, so each run
checks the same cases. The route comes from `risk.advice`, the function `aidd risk --paths` prints, and nothing here computes a
route itself. Each relation returns its first counterexample, and a seeded broken route shows that each one can fail.
"""

import functools
import json
import random
import unittest
from collections.abc import Callable

import helpers  # noqa: F401  (puts src on sys.path)

from aidd import config, knowledge, risk
from aidd.cli import arguments
from aidd.kernel import globs

SEED = 483
CASES = 200  # random cases per relation: enough to reach every area, few enough to run in about a second
RANK = config.ROUTE_RANK
# Words that name no risk: a project's own name, a folder, or a file. A word an area matches is dropped, and a test fails when too few are left.
WORDS = ("garden", "orchard", "lumen", "beacon", "quartz", "harbor", "meadow", "tundra", "ember", "willow", "cobalt", "saffron")
# The usual source file extension of each language in schemas/languages.json, one column for each. The same file in another
# language is the same change. Every extension of a language counts as one of its source files.
EXTENSIONS = tuple(helpers.language_columns().values())
SOURCE_EXTENSIONS = tuple(e.removeprefix(".") for e in config.source_extensions())
# Where a project's own name sits in a path, and what follows it. `{project}` is the project's name, `{ext}` a source extension.
TEMPLATES = (
    "src/{project}/payments/refund.{ext}",
    "src/{project}/auth/session.{ext}",
    "src/{project}/billing/invoice.{ext}",
    "src/{project}/orders/handler.{ext}",
    "src/{project}/utils/strings.{ext}",
    "{project}/api/routes.{ext}",
    "packages/{project}/src/index.{ext}",
    "apps/{project}/db/migrations/0001_init.sql",
    "services/{project}/crypto/keys.{ext}",
    "docs/{project}/guide.md",
    "infra/{project}/main.tf",
    "tests/{project}/test_orders.{ext}",
)
CHANGE_TYPES = ("feat", "fix", "docs", "refactor", "chore")
# A tool's own file: its name is the tool's, never a choice of language, so it has no twin in another one. By file name, and why.
TOOL_FILES = {
    ".pnpmfile.cjs": "pnpm's hook file, which only JavaScript can write",
    "Package.swift": "Swift Package Manager's manifest",
    "__init__.py": "the file that makes a folder a Python package",
    "conftest.py": "pytest's fixture file",
    "noxfile.py": "nox's session file",
    "pytest_plugins.py": "a pytest plugin module",
    "serverless.js": "the Serverless Framework's config in JavaScript",
    "serverless.ts": "the Serverless Framework's config in TypeScript",
    "setup.py": "setuptools' build script",
    "sitecustomize.py": "a file Python runs at every start",
    "usercustomize.py": "a file Python runs at every start for one user",
}
# A built-in area that names a file in one language only, so the same file in another one routes lower: a gap in the risk rules,
# with the backlog row that closes it. It only shrinks: when the rules close a gap, the test says to remove it.
KNOWN_LANGUAGE_GAPS: dict[str, str] = {}

Route = Callable[..., str]


def advised(paths, cfg=None, *, change_type: str = "feat", dimensions=()) -> str:
    """The route `aidd risk --paths` gives."""
    return risk.advice(cfg, list(paths), change_type=change_type, declared=risk.DeclaredRisk(tuple(dimensions)))["route"]


def areas(paths) -> list[str]:
    return [a["area"] for a in risk.advice(None, list(paths))["areas"]]


@functools.cache
def area_samples() -> tuple[str, ...]:
    """A path inside each pattern of each built-in area, kept only where `aidd risk` puts it in an area."""
    out = set()
    for area in risk.builtin()["areas"].values():
        for pattern in area.get("paths", []):
            for path in (globs.sample_path(pattern), pattern):
                if not any(c in path for c in "*?[") and areas([path]):
                    out.add(path)
    return tuple(sorted(out))


@functools.cache
def neutral_files() -> tuple[str, ...]:
    """Files in no area: a word as a folder and a file, with a plain extension."""
    paths = [f"{folder}/{name}.{ext}" for folder in WORDS[:6] for name in WORDS[6:] for ext in ("txt", "csv", "png")]
    return tuple(p for p in paths if not areas([p]))


@functools.cache
def neutral_words() -> tuple[str, ...]:
    """The words that, as a project's name, put a path in no area of their own."""
    return tuple(w for w in WORDS if not areas([f"{w}/{w}.txt", f"src/{w}/{w}.txt"]))


def project_config(work: str, stack: list[str]) -> config.Config:
    return config.load_text(
        f'aidd_version: "1.0.0"\nprofile: team\nproject:\n  work: {work}\n  stack:\n    adopt: [{", ".join(json.dumps(s) for s in stack)}]\n'
    )


def draw(rng: random.Random, low: int = 1, high: int = 5) -> list[str]:
    pool = area_samples() + neutral_files()
    return rng.sample(pool, rng.randint(low, high))


# Each relation draws its cases and returns the first one where `route` breaks it, or None.


def config_names_no_route(route: Route, rng: random.Random):
    stacks = knowledge.stacks()
    base = project_config("product", [])
    for _ in range(CASES // 4):
        paths = draw(rng)
        stack = stacks[rng.choice(sorted(stacks))]
        adopt = [str(x) for x in ((stack.get("project") or {}).get("stack") or {}).get("adopt", [])]
        other = project_config(rng.choice(["product", "client"]), adopt)
        if route(paths, other) != route(paths, base):
            return paths, other.raw["project"]
    return None


def renaming_the_project_folder(route: Route, rng: random.Random):
    for _ in range(CASES):
        templates, ext = rng.sample(TEMPLATES, rng.randint(1, 3)), rng.choice(EXTENSIONS)
        a, b = rng.sample(neutral_words(), 2)
        first, second = ([t.format(project=p, ext=ext) for t in templates] for p in (a, b))
        if route(second) != route(first):
            return first, second
    return None


def in_language(path: str, ext: str) -> str:
    """`path` as a source file in the language of `ext`: its extension swapped, or added to a name that has none."""
    folder, _, name = path.rpartition("/")
    stem = name.rsplit(".", 1)[0] if name.rsplit(".", 1)[-1] in SOURCE_EXTENSIONS else name
    return f"{folder}/{stem}.{ext}" if folder else f"{stem}.{ext}"


def language_gap(path: str) -> str | None:
    """The known gap a file falls in, or None."""
    name = path.rpartition("/")[2]
    return next((row for pattern, row in KNOWN_LANGUAGE_GAPS.items() if globs.match(pattern, name)), None)


def source_file(path: str) -> bool:
    """A file written in a language: its name has a source extension, or it stands for any file (`x` or `y`, a pattern's wildcard).
    A config file, such as CODEOWNERS or a Dockerfile, is in no language, so it has no twin."""
    name = path.rpartition("/")[2]
    return name in ("x", "y") or name.rsplit(".", 1)[-1] in SOURCE_EXTENSIONS and "." in name


@functools.cache
def language_samples() -> tuple[str, ...]:
    """Every area sample that is a source file, is no tool's own file, and falls in no known gap: the files the relation draws."""
    return tuple(p for p in area_samples() if source_file(p) and p.rpartition("/")[2] not in TOOL_FILES and not language_gap(p))


def another_language(route: Route, rng: random.Random):
    """Every file of the pool in every column of the language table: one route for all its languages, so no column is left to
    chance and a language added as a row is a column here at once."""
    for path in language_samples():
        kind = rng.choice(CHANGE_TYPES)
        routes = {ext: route([in_language(path, ext)], change_type=kind) for ext in EXTENSIONS}
        if len(set(routes.values())) > 1:
            return path, kind, routes
    return None


def order_and_repeats(route: Route, rng: random.Random):
    for _ in range(CASES):
        paths = draw(rng, 2, 6)
        for other in (rng.sample(paths, len(paths)), [*paths, rng.choice(paths)]):
            if route(other) != route(paths):
                return paths, other
    return None


def a_file_in_no_area(route: Route, rng: random.Random):
    for _ in range(CASES):
        paths, extra, kind = draw(rng), rng.choice(neutral_files()), rng.choice(CHANGE_TYPES)
        if route([*paths, extra], change_type=kind) != route(paths, change_type=kind):
            return paths, extra, kind
    return None


def more_paths_never_lower(route: Route, rng: random.Random):
    """A bigger change is never a smaller route: each area a path hits raises the route to at least the area's own, and nothing a
    path adds lowers it (docs/METHOD.md, section 4.1 Routes: "An area rule raises the route")."""
    for _ in range(CASES):
        first, second, kind = draw(rng), draw(rng), rng.choice(CHANGE_TYPES)
        both = RANK[route(first + second, change_type=kind)]
        if both < RANK[route(first, change_type=kind)] or both < RANK[route(second, change_type=kind)]:
            return first, second, kind
    return None


def a_risky_path_counts(route: Route, rng: random.Random):
    risky = [p for p in area_samples() if advised([p]) == "major"]
    for _ in range(CASES):
        paths = [*draw(rng), rng.choice(risky)]
        rng.shuffle(paths)
        if route(paths) != "major":
            return paths
    return None


def the_type_names_no_route(route: Route, rng: random.Random):
    """A change type is the commit's word for the change, never its risk: the same paths under every type take one route."""
    for _ in range(CASES // 8):
        paths = draw(rng)
        routes = {t: route(paths, change_type=t) for t in arguments.CHANGE_TYPES}
        if len(set(routes.values())) > 1:
            return paths, routes
    return None


def a_declared_dimension_counts(route: Route, rng: random.Random):
    """A declared dimension raises the route as an area's does: to major for one that forces major, to at least normal for any
    other, and never below what the paths alone take."""
    for _ in range(CASES // 4):
        paths, dimension = draw(rng), rng.choice(arguments.DIMENSIONS)
        floor = "major" if dimension in config.MAJOR_DIMENSIONS else "normal"
        if route(paths, dimensions=[dimension]) != max(route(paths), floor, key=RANK.__getitem__):
            return paths, dimension
    return None


RELATIONS = {
    "the config names no route": config_names_no_route,
    "renaming the project folder never changes a route": renaming_the_project_folder,
    "the same files in another language take the same route": another_language,
    "the order of the paths and a repeat never change a route": order_and_repeats,
    "adding a file in no area never changes a route": a_file_in_no_area,
    "adding paths never lowers a route": more_paths_never_lower,
    "a risky path in a change always counts": a_risky_path_counts,
    "the change type never changes a route": the_type_names_no_route,
    "a declared dimension raises a route to its floor": a_declared_dimension_counts,
}


def _broken(rule: Callable[[list[str], object], str | None]) -> Route:
    """The real route, except where `rule` names another one: a seeded defect a relation must catch."""

    def route(paths, cfg=None, *, change_type: str = "feat", dimensions=()) -> str:
        return rule(list(paths), cfg) or advised(paths, cfg, change_type=change_type, dimensions=dimensions)

    return route


def _raised_by_a_type(paths, cfg=None, *, change_type: str = "feat", dimensions=()) -> str:
    return "major" if change_type == "build" else advised(paths, cfg, change_type=change_type, dimensions=dimensions)


def _declared_read_as_nothing(paths, cfg=None, *, change_type: str = "feat", dimensions=()) -> str:
    return advised(paths, cfg, change_type=change_type)


# A broken route for each relation, as a defect a real change could bring: what it does wrong, and the relation that catches it.
MUTANTS = {
    "a route read from the project's kind of work in the config": (
        _broken(lambda paths, cfg: "major" if cfg is not None and cfg.get("project", "work") == "client" else None),
        "the config names no route",
    ),
    "a route read from the project's folder": (
        _broken(lambda paths, cfg: "major" if any("/lumen/" in f"/{p}" for p in paths) else None),
        "renaming the project folder never changes a route",
    ),
    "a route read from one language's extension": (
        _broken(lambda paths, cfg: "major" if any(p.endswith(".php") for p in paths) else None),
        "the same files in another language take the same route",
    ),
    "a route read from the first path only": (_broken(lambda paths, cfg: advised(paths[:1])), "the order of the paths and a repeat never change a route"),
    "a route raised by the number of files": (
        _broken(lambda paths, cfg: "normal" if len(paths) > 4 else None),
        "adding a file in no area never changes a route",
    ),
    "a large change read as a small one": (_broken(lambda paths, cfg: "minor" if len(paths) > 6 else None), "adding paths never lowers a route"),
    "a risky path missed behind a file in no area": (
        _broken(lambda paths, cfg: advised(paths[:1]) if not areas(paths[:1]) else None),
        "a risky path in a change always counts",
    ),
    "a route raised by one change type": (_raised_by_a_type, "the change type never changes a route"),
    "a declared dimension read as nothing, as before 1.0.0": (_declared_read_as_nothing, "a declared dimension raises a route to its floor"),
}


class Inputs(unittest.TestCase):
    """The drawn inputs are wide enough to mean something, so a relation cannot pass on an empty or a one-area pool."""

    def test_the_pools_reach_every_route_and_most_areas(self):
        samples = area_samples()
        self.assertGreaterEqual(len({a for p in samples for a in areas([p])}), len(risk.builtin()["areas"]) * 3 // 4)
        self.assertEqual({advised([p]) for p in samples} | {advised([neutral_files()[0]])}, {"minor", "normal", "major"})
        self.assertGreaterEqual(len(neutral_files()), 50)
        self.assertGreaterEqual(len(neutral_words()), 8)
        self.assertTrue(any(advised([p]) == "major" for p in samples))


class LanguageExceptions(unittest.TestCase):
    """The files the language relation leaves out are each a tool's own file or a known gap, and each is still needed."""

    def test_each_tool_file_and_each_gap_still_routes_apart_in_another_language(self):
        apart = {}
        for path in filter(source_file, area_samples()):
            others = {advised([in_language(path, ext)]) for ext in EXTENSIONS}
            if len(others | {advised([path])}) > 1:
                apart[path] = others
        for path in apart:
            with self.subTest(path):
                self.assertTrue(path.rpartition("/")[2] in TOOL_FILES or language_gap(path), f"{path} routes apart in another language")
        names = {p.rpartition("/")[2] for p in apart}
        for name, reason in TOOL_FILES.items():
            with self.subTest(name):
                self.assertTrue(reason.strip())
                self.assertIn(name, names, f"{name} routes the same in every language now: remove it from TOOL_FILES")
        for pattern, row in KNOWN_LANGUAGE_GAPS.items():
            with self.subTest(pattern):
                self.assertTrue(row.startswith("R"), "a gap names its backlog row")
                self.assertTrue(any(globs.match(pattern, n) for n in names), f"{pattern} is closed: remove it from KNOWN_LANGUAGE_GAPS")

    def test_the_language_pool_reaches_most_areas(self):
        samples = language_samples()
        self.assertGreaterEqual(len({a for p in samples for a in areas([in_language(p, "go")])}), len(risk.builtin()["areas"]) * 3 // 4)


class Relations(unittest.TestCase):
    def test_each_relation_holds_for_the_route_aidd_gives(self):
        for n, (name, relation) in enumerate(RELATIONS.items()):
            with self.subTest(name):
                self.assertIsNone(relation(advised, random.Random(SEED + n)), "a counterexample: the inputs, then the input the route changed on")

    def test_each_relation_catches_a_seeded_broken_route(self):
        names = list(RELATIONS)
        for label, (broken, catcher) in MUTANTS.items():
            with self.subTest(label):
                self.assertIsNotNone(RELATIONS[catcher](broken, random.Random(SEED + names.index(catcher))), f"{catcher} misses {label}")
        self.assertEqual(sorted(c for _, c in MUTANTS.values()), sorted(RELATIONS), "a seeded defect for each relation")

    def test_every_language_of_the_table_is_a_column_the_language_relation_catches(self):
        """A route that reads one language's extension is caught whichever language it is, so a language added as a row to
        schemas/languages.json is checked at once and nobody lists it again."""
        relation = RELATIONS["the same files in another language take the same route"]
        for language, ext in helpers.language_columns().items():
            with self.subTest(language=language):
                broken = _broken(lambda paths, cfg, ext=ext: "major" if any(p.endswith(f".{ext}") for p in paths) else None)
                self.assertIsNotNone(relation(broken, random.Random(SEED)), f"a route read from .{ext} files goes unseen")
        self.assertGreaterEqual(len(helpers.language_columns()), 14, "the languages the area stems were first checked in are all still columns")


if __name__ == "__main__":
    unittest.main()
