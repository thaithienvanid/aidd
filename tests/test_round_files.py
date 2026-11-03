"""The round files beside a design have one owner each, a schema: `feedback-round-<N>.json`, which the viewer writes, and
`rounds/<N>/changes.json`, which the agent writes. The viewer's export, the prototype tool's reader, and the README's
examples all match it, and `aidd validate` warns on a file that does not."""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from helpers import PROTOTYPE_TOOL, ROOT

from aidd.kernel import json_schema, resources
from aidd.workitems import explorations

FEEDBACK = resources.load_json("feedback-round.schema.json")
CHANGES = resources.load_json("round-changes.schema.json")
VIEWER = (PROTOTYPE_TOOL / "viewer.html").read_text(encoding="utf-8")
README = (PROTOTYPE_TOOL / "README.md").read_text(encoding="utf-8")


class SchemaTests(unittest.TestCase):
    def test_the_viewers_export_writes_exactly_the_schemas_fields(self):
        export = re.search(r"const items = \w+\.map\(\(it\) => \(\{(.*?)\}\)\);", VIEWER)
        self.assertIsNotNone(export, "the viewer builds each exported item in one place")
        written = re.findall(r"(\w+):", export.group(1))
        fields = FEEDBACK["properties"]["items"]["items"]["properties"]
        self.assertEqual(sorted(written), sorted(fields), "a field the viewer writes is a field the schema owns, and back")

    def test_the_tools_reader_reads_only_fields_the_schemas_own(self):
        tool = (PROTOTYPE_TOOL / "prototype.py").read_text(encoding="utf-8")
        read = re.search(r'for k in \(("[a-z]+"(?:, "[a-z]+")*)\)', tool)
        self.assertIsNotNone(read)
        fields = set(FEEDBACK["properties"]["items"]["items"]["properties"])
        self.assertLessEqual(set(re.findall(r'"([a-z]+)"', read.group(1))), fields)
        self.assertIn("answers", CHANGES["properties"]["changes"]["items"]["properties"])

    def test_the_readmes_examples_match(self):
        examples = [json.loads(line) for line in README.splitlines() if line.startswith('{"round"') or line.startswith('{"changes"')]
        self.assertEqual(len(examples), 2)
        self.assertEqual(json_schema.validate(examples[0], "feedback-round.schema.json"), [])
        self.assertEqual(json_schema.validate(examples[1], "round-changes.schema.json"), [])

    def test_validate_warns_on_a_round_file_its_schema_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "specs" / "SPEC-1" / "design"
            (folder / "rounds" / "2").mkdir(parents=True)
            (folder / "feedback-round-1.json").write_text(
                '{"round": 1, "items": [{"id": "r1-1", "screen": "s", "state": "empty", "note": "n"}]}', encoding="utf-8"
            )
            self.assertEqual(explorations.round_file_warnings(root, folder), [], "a sound file says nothing")
            (folder / "feedback-round-2.json").write_text('{"round": 0, "items": [{"id": "x"}]}', encoding="utf-8")
            (folder / "rounds" / "2" / "changes.json").write_text("not json", encoding="utf-8")
            found = explorations.round_file_warnings(root, folder)
            self.assertEqual(len(found), 2, found)
            self.assertIn("specs/SPEC-1/design/feedback-round-2.json does not match schemas/feedback-round.schema.json", found[0])
            self.assertIn("specs/SPEC-1/design/rounds/2/changes.json is not JSON", found[1])

    def test_each_schema_is_in_the_repository(self):
        for name in ("feedback-round.schema.json", "round-changes.schema.json"):
            self.assertTrue((ROOT / "schemas" / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
