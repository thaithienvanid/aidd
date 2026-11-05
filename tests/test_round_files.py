"""The round files beside a design have one owner each, a schema: `rounds/<N>/comments.json`, which the viewer writes,
and `rounds/<N>/changes.json`, which the agent writes. The viewer's export, the prototype tool's reader, and the README's
examples all match it, and `aidd validate` warns on a file that does not."""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import PROTOTYPE_TOOL, ROOT

from aidd.kernel import json_schema, resources
from aidd.workitems import explorations

COMMENTS = resources.load_json("round-comments.schema.json")
CHANGES = resources.load_json("round-changes.schema.json")
VIEWER = (PROTOTYPE_TOOL / "viewer.html").read_text(encoding="utf-8")
README = (PROTOTYPE_TOOL / "README.md").read_text(encoding="utf-8")


class SchemaTests(unittest.TestCase):
    def test_the_viewers_export_writes_exactly_the_schemas_fields(self):
        export = re.search(r"const items = \w+\.map\(\(it\) => \(\{(.*?)\}\)\);", VIEWER)
        self.assertIsNotNone(export, "the viewer builds each exported item in one place")
        written = re.findall(r"(\w+):", export.group(1))
        fields = COMMENTS["properties"]["items"]["items"]["properties"]
        self.assertEqual(sorted(written), sorted(fields), "a field the viewer writes is a field the schema owns, and back")

    def test_the_tools_reader_reads_only_fields_the_schemas_own(self):
        tool = (PROTOTYPE_TOOL / "prototype.py").read_text(encoding="utf-8")
        read = re.search(r'for k in \(("[a-z]+"(?:, "[a-z]+")*)\)', tool)
        self.assertIsNotNone(read)
        fields = set(COMMENTS["properties"]["items"]["items"]["properties"])
        self.assertLessEqual(set(re.findall(r'"([a-z]+)"', read.group(1))), fields)
        self.assertIn("answers", CHANGES["properties"]["changes"]["items"]["properties"])

    def test_the_readmes_examples_match(self):
        examples = [json.loads(line) for line in README.splitlines() if line.startswith('{"round"') or line.startswith('{"changes"')]
        self.assertEqual(len(examples), 2)
        self.assertEqual(json_schema.validate(examples[0], "round-comments.schema.json"), [])
        self.assertEqual(json_schema.validate(examples[1], "round-changes.schema.json"), [])

    def test_validate_warns_on_a_round_file_its_schema_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "specs" / "SPEC-1" / "design"
            for n in ("1", "2"):
                (folder / "rounds" / n).mkdir(parents=True)
            (folder / "rounds" / "1" / "comments.json").write_text(
                '{"round": 1, "items": [{"id": "r1-1", "screen": "s", "state": "empty", "comment": "n"}]}', encoding="utf-8"
            )
            self.assertEqual(explorations.round_file_warnings(root, folder), [], "a sound file says nothing")
            (folder / "rounds" / "2" / "comments.json").write_text('{"round": 0, "items": [{"id": "x"}]}', encoding="utf-8")
            (folder / "rounds" / "2" / "changes.json").write_text("not json", encoding="utf-8")
            found = explorations.round_file_warnings(root, folder)
            self.assertEqual(len(found), 2, found)
            self.assertIn("specs/SPEC-1/design/rounds/2/comments.json does not match schemas/round-comments.schema.json", found[0])
            self.assertIn("specs/SPEC-1/design/rounds/2/changes.json is not JSON", found[1])

    def test_validate_checks_each_directions_file_its_name_its_design_and_its_ids(self):
        def comments(*ids: str) -> str:
            return json.dumps({"round": 1, "items": [{"id": i, "screen": "s", "state": "empty", "comment": "n"} for i in ids]})

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "specs" / "SPEC-1" / "explore" / "listing"
            round_one = folder / "rounds" / "1"
            round_one.mkdir(parents=True)
            (folder / "directions").mkdir()
            for d in ("a", "b"):
                (folder / "directions" / f"{d}.html").write_text("<!doctype html>", encoding="utf-8")
            (round_one / "comments-a.json").write_text(comments("a-r1-1"), encoding="utf-8")
            self.assertEqual(explorations.round_file_warnings(root, folder), [], "a direction's sound file says nothing")
            files = {
                "comments-a.json": comments("a-r1-1", "b-r1-2"),  # another direction's id
                "comments-b.json": '{"round": 1, "items": [{"id": "b-1"}]}',  # the schema rejects it
                "comments-b_2.json": comments("r1-1"),  # no direction's name
                "comments-zzz.json": comments("zzz-r1-1"),  # no directions/zzz.html
                "comments.json": comments("zz-r1-1"),  # a design's own file, with a direction's id
            }
            for name, text in files.items():
                (round_one / name).write_text(text, encoding="utf-8")
            found = explorations.round_file_warnings(root, folder)
        text = "\n".join(found)
        for want in (
            "rounds/1/comments-a.json holds b-r1-2, the ids of another direction",
            "rounds/1/comments-b.json does not match schemas/round-comments.schema.json",
            "rounds/1/comments-b_2.json names no direction",
            "rounds/1/comments-zzz.json names the direction `zzz`, but directions/zzz.html is not in the folder",
            "rounds/1/comments.json holds zz-r1-1, the ids of another direction",
        ):
            self.assertIn(want, text)
        self.assertEqual(len(found), 5, found)

    def test_a_rounds_comments_files_leave_out_a_link_a_way_out_a_large_file_and_any_past_the_cap(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as away:
            top = Path(tmp)
            round_one = top / "rounds" / "1"
            round_one.mkdir(parents=True)
            outside = Path(away) / "comments-a.json"
            outside.write_text("{}", encoding="utf-8")
            (round_one / "comments-a.json").symlink_to(outside)
            (top / "rounds" / "2").symlink_to(Path(away), target_is_directory=True)  # a round folder that leads out
            (round_one / "comments-b.json").write_text("x" * 11, encoding="utf-8")
            for i in range(explorations.MAX_DIRECTION_FILES + 1):
                (round_one / f"comments-d{i:02d}.json").write_text("{}", encoding="utf-8")
            with mock.patch.object(explorations, "MAX_LINT_BYTES", 10):
                kept, left_out = explorations.round_comment_files(round_one, top)
                _, led_out = explorations.round_comment_files(top / "rounds" / "2", top)
        text = "\n".join(left_out)
        self.assertIn("comments-a.json is left out: it is a link", text)
        self.assertIn("comments-b.json is left out: it is a link, leads out of the folder, or is larger than 10 bytes", text)
        self.assertIn(f"comments-d{explorations.MAX_DIRECTION_FILES:02d}.json is left out: a round reads the comments of", text)
        self.assertLessEqual(len(kept), explorations.MAX_DIRECTION_FILES)
        self.assertEqual([name for name, _ in kept][:2], ["d00", "d01"])
        self.assertTrue(led_out and led_out[0].startswith("comments-a.json is left out"), led_out)

    def test_each_schema_is_in_the_repository(self):
        for name in ("round-comments.schema.json", "round-changes.schema.json"):
            self.assertTrue((ROOT / "schemas" / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
