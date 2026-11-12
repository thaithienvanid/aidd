"""The shared graders of the live suites have one text in evals/library/graders/, and every case's copy matches it."""

import json
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd.evals import grader_library as lib
from aidd.kernel import json_schema

GRADER = "---\ntype: tool_used\ntool: Agent\ninput_match: 'aidd-team:architect'\nmin: 1\n---\n"
OTHER = GRADER.replace("architect", "verifier")


def tree(root: Path, copies: dict[str, str], uses: list[str], library: str = GRADER, extra: dict[str, str] | None = None) -> None:
    """A repository with the given cases' graders (`suite/case/stem` and its text), one library grader named `starts-the-architect`
    that `uses` lists, and any `extra` library file."""
    for use, text in copies.items():
        suite, case, stem = use.split("/")
        path = root / "evals" / suite / case / "graders" / f"{stem}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    (root / "evals" / "library" / "graders").mkdir(parents=True, exist_ok=True)
    if uses:
        (root / "evals" / "library" / "graders" / "starts-the-architect.md").write_text(library, encoding="utf-8")
    for name, text in (extra or {}).items():
        (root / "evals" / "library" / "graders" / f"{name}.md").write_text(text, encoding="utf-8")
    index = {"description": "d", "graders": {"starts-the-architect": {"uses": uses}} if uses else {}}
    (root / "evals" / "library" / "graders.json").write_text(json.dumps(index), encoding="utf-8")


class LibraryTests(unittest.TestCase):
    def test_the_shipped_library_follows_its_schema_and_every_copy_matches_it(self):
        index = lib.read_index(ROOT)
        self.assertEqual(json_schema.validate(index, "eval-grader-library.schema.json"), [])
        self.assertEqual(lib.problems(ROOT), [])
        self.assertGreaterEqual(sum(len(e["uses"]) for e in index["graders"].values()), 150, "the shared graders were 199 files in 61 texts")

    def test_the_checker_names_each_way_a_copy_and_the_library_disagree(self):
        a, b = "plugin/one/starts-the-architect", "team/two/product-manager"
        cases = {
            "all copies match": (dict(copies={a: GRADER, b: GRADER}, uses=[a, b]), []),
            "a copy that drifted": (dict(copies={a: GRADER, b: OTHER}, uses=[a, b]), ["differs from the library file"]),
            "a use with no grader in a case": (dict(copies={a: GRADER}, uses=[a, b]), ["is no grader of a case"]),
            "an entry with one use": (dict(copies={a: GRADER}, uses=[a]), ["at least two uses"]),
            "two cases that hold one grader alike and no entry": (dict(copies={a: GRADER, b: GRADER}, uses=[]), ["hold one grader alike"]),
            "a library file no entry names": (dict(copies={a: GRADER, b: GRADER}, uses=[a, b], extra={"orphan": OTHER}), ["a library file no entry names"]),
            "graders that differ and are in no entry": (dict(copies={a: GRADER, b: OTHER}, uses=[]), []),
        }
        for name, (build, want) in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                tree(Path(tmp), **build)
                got = lib.problems(Path(tmp))
                self.assertEqual(len(got), len(want), got)
                for fragment, line in zip(want, got, strict=True):
                    self.assertIn(fragment, line)

    def test_writing_the_copies_repairs_a_drifted_one_and_changes_nothing_else(self):
        a, b = "plugin/one/starts-the-architect", "team/two/product-manager"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tree(root, {a: GRADER, b: OTHER}, [a, b])
            self.assertEqual(lib.write_copies(root), ["evals/team/two/graders/product-manager.md"])
            self.assertEqual(lib.problems(root), [])
            self.assertEqual(lib.write_copies(root), [])

    def test_adopting_the_shared_graders_names_each_by_its_commonest_file_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copies = {
                "plugin/one/starts-the-architect": GRADER,
                "team/two/product-manager": GRADER,
                "team/three/starts-the-architect": GRADER,
                "team/four/unique": OTHER,
            }
            tree(root, copies, [])
            self.assertEqual(
                lib.adopt(root),
                {
                    "graders": {
                        "starts-the-architect": {"uses": ["plugin/one/starts-the-architect", "team/three/starts-the-architect", "team/two/product-manager"]}
                    }
                },
            )

    def test_the_command_line_checks_and_writes(self):
        a, b = "plugin/one/starts-the-architect", "team/two/product-manager"
        with tempfile.TemporaryDirectory() as tmp:
            tree(Path(tmp), {a: GRADER, b: OTHER}, [a, b])
            self.assertEqual(lib.main(["--check", tmp]), 1)
            self.assertEqual(lib.main([tmp]), 0)
            self.assertEqual(lib.main(["--check", tmp]), 0)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(lib.main([tmp]), 2, "a folder with no index is not a checkout")


if __name__ == "__main__":
    unittest.main()
