"""`[project.writing] controlled`: the doc types a project writes at the `controlled` writing level, ASD-STE100 Simplified Technical English.

The key only records the opt-in, for the plain-language practice skill to read. It takes a closed list of the doc types aidd
knows, and it is empty unless set. A parent that locks `project` keeps its types: a child adds to them.
"""

import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd import config
from aidd.config import project
from aidd.kernel import documents, json_schema, resources

HEAD = 'aidd_version: "1.0.0"\nprofile: team\n\nowners:\n  approvers: ["@x"]\n'


def valid(writing: dict) -> list[str]:
    return json_schema.validate(dict(documents.parse_yaml(HEAD, "c"), project={"writing": writing}), "config.schema.json")


class WritingConfigTests(unittest.TestCase):
    def test_the_types_are_the_doc_types_aidd_knows(self):
        prop = resources.load_json("config.schema.json")["properties"]["project"]["properties"]["writing"]
        self.assertEqual(list(prop["properties"]), ["controlled"])
        enum = prop["properties"]["controlled"]["items"]["enum"]
        self.assertEqual(set(enum), set(config.item_type_rows()) - {"product-prototype"})  # each type `aidd new` writes as prose
        self.assertEqual(enum, sorted(enum))
        self.assertEqual(prop["properties"]["controlled"]["default"], [])

    def test_the_schema_takes_known_types_only(self):
        self.assertEqual(valid({"controlled": ["spec", "adr", "runbook"]}), [])
        self.assertEqual(valid({"controlled": []}), [])
        self.assertTrue(valid({"controlled": ["novel"]}))
        self.assertTrue(valid({"controlled": ["spec", "spec"]}))
        self.assertTrue(valid({"controlled": "spec"}))
        self.assertTrue(valid({"plain": True}))

    def test_it_is_empty_unless_set_and_read_as_written(self):
        self.assertEqual(config.load_text(HEAD).get("project", "writing", "controlled", default=[]), [])
        cfg = config.load_text(HEAD + "\nproject:\n  writing:\n    controlled: [spec, runbook]\n")
        self.assertEqual(cfg.get("project", "writing", "controlled", default=[]), ["spec", "runbook"])

    def test_a_locked_parent_keeps_its_types(self):
        parent, child = {"writing": {"controlled": ["spec"]}}, {"writing": {"controlled": ["adr"]}}
        self.assertEqual(project.merge(parent, child, locked=True, where="c", warnings=[])["writing"], {"controlled": ["spec", "adr"]})
        self.assertEqual(project.merge(parent, child, locked=False, where="c", warnings=[])["writing"], {"controlled": ["adr"]})

    def test_a_real_parent_config_file_merges_the_types(self):
        """Through `extends` and the files on disk: locked, the parent's types stay and the child's join them."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".aidd").mkdir()
            parent = HEAD + "\nproject:\n  writing:\n    controlled: [spec, runbook]\n"
            child = HEAD.replace("profile", "extends: [{path: .aidd/parent.yaml}]\nprofile") + "\nproject:\n  writing:\n    controlled: [adr, spec]\n"
            (root / ".aidd" / "config.yaml").write_text(child, encoding="utf-8")
            for lock, want in (("", ["adr", "spec"]), ("locks: [project]\n", ["spec", "runbook", "adr"])):
                with self.subTest(locked=bool(lock)):
                    (root / ".aidd" / "parent.yaml").write_text(lock + parent, encoding="utf-8")
                    cfg = config.load_file(".aidd/config.yaml", str(root))
                    self.assertEqual(cfg.get("project", "writing", "controlled"), want)

    def test_the_old_key_fails_with_the_new_key_and_the_command_that_moves_it(self):
        """No silent default: a config that still says `ste_100` is not read as an empty `controlled`."""
        for name, writing in (("one type", "[spec]"), ("empty", "[]"), ("several", "[spec, runbook, adr]")):
            with self.subTest(name):
                with self.assertRaises(config.ConfigError) as caught:
                    config.load_text(HEAD + f"\nproject:\n  writing:\n    ste_100: {writing}\n")
                message = str(caught.exception)
                self.assertIn("`project.writing.ste_100` was retired in 1.0.0", message)
                self.assertIn("`controlled`", message)
                self.assertIn("aidd upgrade --yes", message)

    def test_config_md_documents_it_from_the_schema(self):
        self.assertIn("<!-- aidd:gen fields:config-project-writing -->", (ROOT / "docs" / "CONFIG.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
