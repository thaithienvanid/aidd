"""The languages' table (schemas/languages.json) is the one place aidd learns which files are source and which manifests name a
project, so a repository in any language gets the same advice and another language is a row. Three things hold:

- Moving the lists into data lost nothing. The extensions `aidd risk` and `aidd init` knew before the table (`START`, kept below) are
  all still source, the manifests `aidd init` opens are the ones it opened, and the table adds only what ADDED names.
- Every language is a column. One list, `helpers.language_columns`, feeds the tests that write a file in each language (the area
  stems and the route relations), and it holds the languages those tests first checked in.
- The advice that reads the table gives the same next step for a new feature file in every language, and none for a file that
  is not source.

Which files are tests stays in `test_paths` of schemas/risks.json, and the runners in schemas/test-runners.json.
"""

from __future__ import annotations

import itertools
import json
import unittest
from unittest import mock

import helpers  # noqa: F401  # the hermetic environment
from helpers import ROOT

from aidd import config
from aidd.kernel import json_schema, resources
from aidd.risk import routes

DATA = json.loads((ROOT / "schemas" / "languages.json").read_text(encoding="utf-8"))
LANGUAGES = DATA["languages"]

# The lists before the table, as they stood at the commit this package started from (5fb351ad).
START_ROUTES = (".py", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".kt", ".cs", ".rb", ".php", ".ex", ".dart", ".swift")
START_INIT = (".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt", ".rb", ".cs", ".php", ".dart", ".swift")
START_MANIFESTS = frozenset(
    {
        "package.json", "pyproject.toml", "setup.cfg", "requirements.txt", "setup.py", "go.mod", "Cargo.toml", "pom.xml", "build.gradle",
        "build.gradle.kts", "Gemfile", "pubspec.yaml", "composer.json", "deno.json", "deno.jsonc", "Package.swift", "mix.exs", "build.sbt",
        "CMakeLists.txt", "Makefile",
    }
)  # fmt: skip
# The languages the area stems and the route relations were first checked in, by the extension of their usual file.
FIRST_COLUMNS = ("py", "ts", "js", "go", "rs", "java", "kt", "cs", "rb", "php", "swift", "dart", "c", "cpp")
# What the table adds to the lists before it: source a language writes that no list named, so a new file of it now asks for its test.
ADDED = {".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".scala"}
ADDED_TO_INIT = ADDED | {".mjs", ".cjs", ".ex"}  # `aidd init` also counts the module and the Elixir files `aidd risk` already knew


class TheTableLostNothing(unittest.TestCase):
    def test_every_extension_the_lists_held_is_source_still_and_the_table_adds_only_what_is_named(self):
        table = set(config.source_extensions())
        self.assertLessEqual(set(START_ROUTES) | set(START_INIT), table)
        self.assertEqual(table - set(START_ROUTES), ADDED)
        self.assertEqual(table - set(START_INIT), ADDED_TO_INIT)

    def test_aidd_init_opens_the_manifests_it_opened_and_no_other(self):
        self.assertEqual(config.manifest_names(), START_MANIFESTS)

    def test_the_languages_the_stem_tests_first_checked_are_all_columns(self):
        self.assertLessEqual(set(FIRST_COLUMNS), set(helpers.language_columns().values()))
        self.assertEqual(tuple(helpers.language_columns()), tuple(LANGUAGES))


class InitOpensOnlyTheManifestsOfTheTable(unittest.TestCase):
    def test_a_file_is_opened_when_its_name_is_in_the_table_and_never_otherwise(self):
        from pathlib import Path

        from aidd.setup import detection

        opened: list[str] = []
        with mock.patch.object(detection, "_read", side_effect=lambda p, *a, **k: opened.append(p.name) or ""):
            for name in [*sorted(config.manifest_names()), "README.md", "notes.txt", "package.json.bak", "pom.xml.orig", "Makefile.d"]:
                detection._stack(Path("/repo", name), Path("/repo"))
        self.assertEqual(set(opened), config.manifest_names(), "a manifest may be read twice (its package manager), a file of another name never")

    def test_a_manifest_added_as_a_row_is_opened_at_once(self):
        from pathlib import Path

        from aidd.setup import detection

        real = resources.load_json
        table = json.loads(json.dumps(real("languages.json")))
        table["languages"]["zig"] = {"extensions": [".zig"], "manifests": ["build.zig"]}
        config.manifest_names.cache_clear()
        opened: list[str] = []
        try:
            with (
                mock.patch.object(resources, "load_json", side_effect=lambda name, *a, **k: table if name == "languages.json" else real(name, *a, **k)),
                mock.patch.object(detection, "_read", side_effect=lambda p, *a, **k: opened.append(p.name) or ""),
            ):
                detection._stack(Path("/repo/build.zig"), Path("/repo"))
        finally:
            config.manifest_names.cache_clear()
        self.assertEqual(set(opened), {"build.zig"})


class TheTableFollowsItsSchema(unittest.TestCase):
    def test_the_file_follows_the_schema(self):
        self.assertEqual(json_schema.validate(DATA, "languages.schema.json"), [])

    def test_languages_are_in_alphabetical_order_and_their_extensions_in_the_order_the_schema_gives(self):
        self.assertEqual(list(LANGUAGES), sorted(LANGUAGES))
        for name, row in LANGUAGES.items():
            with self.subTest(language=name):
                self.assertEqual(row["extensions"][1:], sorted(row["extensions"][1:]), "the usual extension first, the rest alphabetical")
                self.assertEqual(row.get("manifests", []), sorted(row.get("manifests", [])))

    def test_one_extension_and_one_manifest_belong_to_one_language(self):
        extensions = [e for row in LANGUAGES.values() for e in row["extensions"]]
        self.assertEqual(len(extensions), len(set(extensions)), "an extension is two languages' source")
        manifests = [m for row in LANGUAGES.values() for m in row.get("manifests", [])] + DATA["manifests_of_any_language"]
        self.assertEqual(len(manifests), len(set(manifests)), "a manifest is two languages'")

    def test_a_language_row_holds_no_test_pattern_and_no_runner_exit(self):
        """Their owners are `test_paths` and schemas/test-runners.json: this file restates none."""
        for row in LANGUAGES.values():
            self.assertLessEqual(set(row), {"extensions", "manifests", "gitignore"})


class TheAdviceIsTheSameInEveryLanguage(unittest.TestCase):
    def untested(self, *paths: str, change_type: str = "feat", tracked: tuple[str, ...] = ()) -> str | None:
        return routes.untested_new_files(list(paths), change_type=change_type, tracked=list(tracked))

    def test_a_new_feature_file_asks_for_its_test_first_in_every_extension_of_every_language(self):
        for name, row in LANGUAGES.items():
            for ext in row["extensions"]:
                path = f"src/billing/invoice{ext}"
                with self.subTest(language=name, path=path):
                    self.assertEqual(self.untested(path), path)

    def test_the_same_file_in_each_language_asks_for_the_same_thing_in_every_case(self):
        """Over every language and the cases that decide it: only a new source file of a feature that names no test asks."""
        for (name, row), (kind, known, with_test, folder) in itertools.product(
            LANGUAGES.items(), itertools.product(("feat", "fix", "docs", "refactor"), (False, True), (False, True), ("src/", "lib/api/", ""))
        ):
            ext = row["extensions"][0]
            path = f"{folder}widget{ext}"
            paths = [path, f"tests/widget_test{ext}"] if with_test else [path]
            expected = path if kind == "feat" and not known and not with_test else None
            with self.subTest(language=name, change_type=kind, known=known, with_test=with_test, folder=folder):
                self.assertEqual(self.untested(*paths, change_type=kind, tracked=(path,) if known else ()), expected)

    def test_a_file_that_is_not_source_asks_for_nothing(self):
        for path in ("docs/guide.md", "src/data.json", "src/widget.zzz", "Makefile", "src/widget", "src/widget.PY.txt", "src/widgetpy"):
            with self.subTest(path=path):
                self.assertIsNone(self.untested(path))

    def test_a_row_added_to_the_table_is_read_at_once(self):
        """Another language is a row and no code: the reader takes its extension from the data, never from a list in the code."""
        real = resources.load_json
        table = json.loads(json.dumps(real("languages.json")))
        table["languages"]["zig"] = {"extensions": [".zig"], "manifests": ["build.zig"], "gitignore": ["zig-cache/", ".zig-cache/", "zig-out/"]}
        config.source_extensions.cache_clear()
        config.manifest_names.cache_clear()
        config.language_gitignore.cache_clear()
        config.manifest_languages.cache_clear()
        try:
            with mock.patch.object(resources, "load_json", side_effect=lambda name, *a, **k: table if name == "languages.json" else real(name, *a, **k)):
                self.assertEqual(self.untested("src/main.zig"), "src/main.zig")
                self.assertIn("build.zig", config.manifest_names())
                self.assertEqual(config.language_gitignore()["zig"], ("zig-cache/", ".zig-cache/", "zig-out/"))
        finally:
            config.source_extensions.cache_clear()
            config.manifest_names.cache_clear()
            config.language_gitignore.cache_clear()
            config.manifest_languages.cache_clear()
        self.assertIsNone(self.untested("src/main.zig"))

    def test_a_row_with_gitignore_is_detected_by_init_with_no_code_change(self):
        import tempfile
        from pathlib import Path

        from aidd.setup import detection, ignore_lines

        real = resources.load_json
        table = json.loads(json.dumps(real("languages.json")))
        table["languages"]["zig"] = {"extensions": [".zig"], "manifests": ["build.zig"], "gitignore": ["zig-cache/", ".zig-cache/", "zig-out/"]}
        config.manifest_names.cache_clear()
        config.language_gitignore.cache_clear()
        config.manifest_languages.cache_clear()
        try:
            with (
                tempfile.TemporaryDirectory() as d,
                mock.patch.object(resources, "load_json", side_effect=lambda name, *a, **k: table if name == "languages.json" else real(name, *a, **k)),
            ):
                root = Path(d).resolve()
                (root / "build.zig").write_text("// build\n", encoding="utf-8")
                langs = detection.language_names(root)
                lines = ignore_lines.missing_ignore_lines(root, "", langs)
                self.assertIn("zig", langs)
                self.assertEqual(
                    lines, [ignore_lines.TEST_OUTPUTS_MARK, "zig-cache/", ".zig-cache/", "zig-out/", ignore_lines.OS_FILES_MARK, *ignore_lines.OS_FILES]
                )
        finally:
            config.manifest_names.cache_clear()
            config.language_gitignore.cache_clear()
            config.manifest_languages.cache_clear()


if __name__ == "__main__":
    unittest.main()
