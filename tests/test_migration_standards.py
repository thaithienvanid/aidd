"""A library standard's `source` and `evidence` became one `citation: {url, quote}` (schemas/retired-names.json, surface `standard`).

The invariant: an adopter's copy keeps every value it held and every line it did not name. An edited copy moves by `aidd upgrade --yes`;
an unedited one is written again from the library; a copy that cannot move stays, and a line says why; `aidd doctor` names the new
keys of a copy still in the old shape. aidd's own library moves by the same function (`yaml_edit.gather`), so the two cannot differ."""

import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from migration_fixture import CONFIG, FIXTURES, Repo

from aidd import config, knowledge
from aidd.kernel import documents, json_schema, resources, yaml_edit
from aidd.knowledge import standards
from aidd.setup import migrating

COPY = "docs/standards/python/ruff-lint-format.md"
URL, QUOTE = "https://pypi.org/pypi/ruff/json", '"\\"version\\":\\"0.17.1\\""'
HEAD = "---\nid: python/ruff-lint-format\ntype: opinionated\nchecked: '2026-10-20'\n"
TAIL = "status: active\n---\n\nBody.\n"
# The two old keys as a person may have left them, each with what must come out under `citation`.
OLD_SHAPES = {
    "url then quote": ('source: https://a.example/p\nevidence: "A full sentence from the page."\n', "https://a.example/p", "A full sentence from the page."),
    "quote then url": ("evidence: Plain words, with C# in them.\nsource: https://a.example/p\n", "https://a.example/p", "Plain words, with C# in them."),
    "comments stay": ("source: https://a.example/p   # the feed\nevidence: Two words.  # read\n", "https://a.example/p", "Two words."),
    "single quotes": ("source: 'https://a.example/p'\nevidence: 'It''s there.'\n", "https://a.example/p", "It's there."),
    "keys apart": ("source: https://a.example/p\nchecked_by: '@x'\nevidence: x y\n", "https://a.example/p", "x y"),
}
# Shapes the move leaves alone, because a guess could lose a value: the text each one holds, and what the line must say.
STAYS = {
    "citation beside the old keys": ("citation:\n  url: https://b.example\n  quote: q\nsource: https://a.example/p\nevidence: x y\n", "is set too"),
    "a block scalar": ("source: https://a.example/p\nevidence: |\n  two\n  lines\n", "one line of its own"),
    "a flow collection": ("source: https://a.example/p\nevidence: [a, b]\n", "one line of its own"),
}


def copy_text(keys: str) -> str:
    return HEAD + keys + TAIL


class TheMoveOfOneCopy(Repo):
    """The engine on a copy the config lists, in each shape of the old keys."""

    def move(self, text: str) -> tuple[str | None, list[tuple[str, str]]]:
        (self.root / COPY).write_text(text, encoding="utf-8", newline="")
        found = migrating.plan(self.root)
        return found.texts.get(COPY), [(kind, line) for kind, line in found.lines if line.startswith(f"{COPY}:")]

    def test_each_old_shape_moves_its_two_values_and_changes_no_other_line(self):
        for name, (keys, url, quote) in OLD_SHAPES.items():
            with self.subTest(name):
                old = copy_text(keys)
                new, lines = self.move(old)
                self.assertIsNotNone(new)
                before, after = documents.split_front_matter(old, COPY)[0], documents.split_front_matter(new, COPY)[0]
                self.assertEqual(after.pop("citation"), {"url": url, "quote": quote})
                self.assertEqual(({k: v for k, v in before.items() if k not in ("source", "evidence")}), after, "every other key holds")
                self.assertEqual((before["source"], before["evidence"]), (url, quote), "and the values are the ones the old keys held")
                gone = set(old.splitlines()) - set(new.splitlines())
                self.assertEqual({line.split(":")[0] for line in gone}, {"source", "evidence"})
                self.assertEqual([kind for kind, _ in lines], ["migrate", "migrate"], lines)
                self.assertTrue(all("retired in 1.0.0" in line for _, line in lines))

    def test_a_comment_on_a_moved_line_stays_on_it(self):
        new, _ = self.move(copy_text(OLD_SHAPES["comments stay"][0]))
        self.assertIn("  url: https://a.example/p   # the feed\n", new)
        self.assertIn("  quote: Two words.  # read\n", new)

    def test_line_endings_stay(self):
        new, _ = self.move(copy_text(OLD_SHAPES["url then quote"][0]).replace("\n", "\r\n"))
        self.assertEqual(new.count("\r\n"), new.count("\n"), "no bare line feed was added")
        self.assertEqual(documents.split_front_matter(new, COPY)[0]["citation"]["url"], "https://a.example/p")

    def test_a_shape_that_could_lose_a_value_stays_and_a_line_names_the_way_out(self):
        for name, (keys, said) in STAYS.items():
            with self.subTest(name):
                new, lines = self.move(copy_text(keys))
                self.assertIsNone(new)
                self.assertTrue(lines and all(kind == "manual" for kind, _ in lines), lines)
                self.assertTrue(all(said in line and "`aidd upgrade` again" in line for _, line in lines), lines)

    def test_today_s_shape_and_a_second_run_change_nothing(self):
        today = (FIXTURES / "today" / COPY).read_text(encoding="utf-8")
        self.assertEqual(self.move(today), (None, []))
        new, _ = self.move((FIXTURES / "pre" / COPY).read_text(encoding="utf-8"))
        self.assertEqual(new, today)
        self.assertEqual(self.move(new), (None, []))

    def test_a_copy_aidd_wrote_is_left_to_the_refresh_and_a_path_outside_the_folder_is_not_read(self):
        old = copy_text(OLD_SHAPES["url then quote"][0])
        recorded = f'sha256: "{"0" * 64}"'
        cfg = (self.root / CONFIG).read_text(encoding="utf-8")
        assert recorded in cfg
        (self.root / COPY).write_text(old, encoding="utf-8")
        beyond = tempfile.TemporaryDirectory()  # a file beyond the repository, which a link in the folder points at
        self.addCleanup(beyond.cleanup)
        outside = Path(beyond.name) / "ruff-lint-format.md"
        outside.write_text(old, encoding="utf-8")
        (self.root / "docs" / "standards" / "python" / "link.md").symlink_to(outside)
        (self.root / "docs" / "elsewhere").mkdir()
        (self.root / "docs" / "elsewhere" / "ruff-lint-format.md").write_text(old, encoding="utf-8")  # a file the config lists, outside the folder
        for name, edit in {
            "unedited, an older aidd wrote it": cfg.replace(recorded, f'sha256: "{standards.digest(old)}"'),
            "a path outside the standards folder": cfg.replace(f"path: {COPY}", "path: docs/elsewhere/ruff-lint-format.md"),
            "a path that leaves the repository": cfg.replace(f"path: {COPY}", 'path: "../ruff-lint-format.md"'),
            "a link to a file beyond the repository": cfg.replace(f"path: {COPY}", "path: docs/standards/python/link.md"),
        }.items():
            with self.subTest(name), mock.patch.object(standards, "__version__", "1.9.9"):  # a later aidd than the one that wrote the copy
                (self.root / CONFIG).write_text(edit, encoding="utf-8")
                found = migrating.plan(self.root)
                self.assertEqual({rel for rel in found.texts if "ruff-lint-format" in rel or "link" in rel}, set())
                self.assertFalse([line for _, line in found.lines if "ruff-lint-format" in line], found.lines)


class TheLibraryMovesByTheSameFunction(unittest.TestCase):
    def test_the_move_of_every_library_file_is_the_inverse_of_how_it_was_written_before(self):
        """The 244 files of aidd's library and an adopter's copy move by one function: write each file's old shape back, move it again."""
        for sid, standard in knowledge.standards_library().items():
            text = standard.text
            front = documents.FRONT_MATTER.match(text).group(1)
            url, quote = re.search(r"^  url:(.*)$", front, re.M).group(1), re.search(r"^  quote:(.*)$", front, re.M).group(1)
            old = front.replace(f"citation:\n  url:{url}\n  quote:{quote}", f"source:{url}\nevidence:{quote}")
            self.assertNotEqual(old, front, sid)
            self.assertEqual(yaml_edit.gather(old, "citation", migrating.CITATION_KEYS), front, sid)


class TheCopiesAFullUpgradeHandles(Repo):
    def test_an_unedited_copy_in_the_old_shape_is_written_again_from_the_library(self):
        standard = knowledge.standards_library()["python/ruff-lint-format"]
        front = documents.FRONT_MATTER.match(standard.text).group(1)
        url, quote = re.search(r"^  url:(.*)$", front, re.M).group(1), re.search(r"^  quote:(.*)$", front, re.M).group(1)
        old = standard.text.replace(f"citation:\n  url:{url}\n  quote:{quote}", f"source:{url}\nevidence:{quote}")
        self.assertNotEqual(old, standard.text)
        (self.root / COPY).write_text(old, encoding="utf-8")
        cfg = (self.root / CONFIG).read_text(encoding="utf-8")
        marks = "# aidd:standard python/ruff-lint-format: x\n"
        end = "# aidd:end python/ruff-lint-format\n"
        entry = re.search(r"  - type: standard\n    name: python-ruff-lint-format\n.*?\n(?=\nmcp:)", cfg, re.S).group(0)
        cfg = cfg.replace(entry, "  " + marks + entry + "  " + end)
        cfg = cfg.replace("0" * 64, standards.digest(old))
        (self.root / CONFIG).write_text(cfg, encoding="utf-8")
        with mock.patch.object(standards, "__version__", "1.9.9"):  # a later aidd than the one that wrote the copy
            lines = self.upgrade(yes=True)
        self.assertEqual((self.root / COPY).read_text(encoding="utf-8"), standard.text)
        self.assertFalse([line for line in lines if line.startswith(("migrated", "manual")) and "ruff-lint-format" in line], lines)

    def test_the_doctor_names_the_new_keys_of_an_edited_copy_still_in_the_old_shape(self):
        shape = "today"
        for rel in (CONFIG, COPY):
            (self.root / rel).write_bytes((FIXTURES / shape / rel).read_bytes())
        (self.root / COPY).write_bytes((FIXTURES / "pre" / COPY).read_bytes())
        cfg = config.load_file(CONFIG, str(self.root))
        warns = [w for level, w in knowledge.standard_doctor_checks(self.root, cfg) if level == "warn" and "retired" in w]
        self.assertEqual(len(warns), 1, warns)
        for part in ("`source` is now `citation.url`", "`evidence` is now `citation.quote`", "`aidd upgrade --yes`", "python-ruff-lint-format"):
            self.assertIn(part, warns[0])
        (self.root / COPY).write_bytes((FIXTURES / "today" / COPY).read_bytes())
        self.assertEqual([w for level, w in knowledge.standard_doctor_checks(self.root, cfg) if "retired" in w], [], "the shape of today says nothing")

    def test_a_copy_in_the_old_shape_is_refused_by_the_schema_that_names_its_row(self):
        text = (FIXTURES / "pre" / COPY).read_text(encoding="utf-8")
        errors = json_schema.validate(documents.split_front_matter(text, COPY)[0], "standard.schema.json")
        self.assertTrue(any("unknown field 'source'" in e for e in errors) and any("unknown field 'evidence'" in e for e in errors), errors)
        self.assertEqual({r["old"] for r in resources.load_json("retired-names.json")["retired"] if r["surface"] == "standard"}, {"source", "evidence"})


if __name__ == "__main__":
    unittest.main()
