"""`[project.writing] ste_100`: the doc kinds a project writes in ASD-STE100 Simplified Technical English.

The key only records the opt-in, for the plain-language practice skill to read. It takes a closed list of the doc kinds aidd
knows, and it is empty unless set. A parent that locks `project` keeps its kinds: a child adds to them.
"""

import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd import config as cfgmod
from aidd import model, project, repo, resources, schema

HEAD = 'aidd_version = "1.0.0"\nprofile = "team"\n\n[owners]\napprovers = ["@x"]\n'


def valid(writing: dict) -> list[str]:
    return schema.validate(dict(model.parse_toml(HEAD, "c"), project={"writing": writing}), "config.schema.json")


class WritingConfigTests(unittest.TestCase):
    def test_the_kinds_are_the_doc_kinds_aidd_knows(self):
        prop = resources.load_json("config.schema.json")["properties"]["project"]["properties"]["writing"]
        self.assertEqual(list(prop["properties"]), ["ste_100"])
        enum = prop["properties"]["ste_100"]["items"]["enum"]
        self.assertEqual(set(enum), set(model.OBJECT_SCHEMAS) | set(repo.DOC_KINDS_NEW))
        self.assertEqual(enum, sorted(enum))
        self.assertEqual(prop["properties"]["ste_100"]["default"], [])

    def test_the_schema_takes_known_kinds_only(self):
        self.assertEqual(valid({"ste_100": ["spec", "adr", "runbook"]}), [])
        self.assertEqual(valid({"ste_100": []}), [])
        self.assertTrue(valid({"ste_100": ["novel"]}))
        self.assertTrue(valid({"ste_100": ["spec", "spec"]}))
        self.assertTrue(valid({"ste_100": "spec"}))
        self.assertTrue(valid({"plain": True}))

    def test_it_is_empty_unless_set_and_read_as_written(self):
        self.assertEqual(cfgmod.load_text(HEAD).get("project", "writing", "ste_100", default=[]), [])
        cfg = cfgmod.load_text(HEAD + '\n[project.writing]\nste_100 = ["spec", "runbook"]\n')
        self.assertEqual(cfg.get("project", "writing", "ste_100", default=[]), ["spec", "runbook"])

    def test_a_locked_parent_keeps_its_kinds(self):
        parent, child = {"writing": {"ste_100": ["spec"]}}, {"writing": {"ste_100": ["adr"]}}
        self.assertEqual(project.merge(parent, child, locked=True, where="c", warnings=[])["writing"], {"ste_100": ["spec", "adr"]})
        self.assertEqual(project.merge(parent, child, locked=False, where="c", warnings=[])["writing"], {"ste_100": ["adr"]})

    def test_a_real_parent_config_file_merges_the_kinds(self):
        """Through `extends` and the files on disk: locked, the parent's kinds stay and the child's join them."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".aidd").mkdir()
            parent = HEAD + '\n[project.writing]\nste_100 = ["spec", "runbook"]\n'
            child = HEAD.replace("profile", 'extends = [{ path = ".aidd/parent.toml" }]\nprofile') + '\n[project.writing]\nste_100 = ["adr", "spec"]\n'
            (root / ".aidd" / "config.toml").write_text(child, encoding="utf-8")
            for lock, want in (("", ["adr", "spec"]), ('locks = ["project"]\n', ["spec", "runbook", "adr"])):
                with self.subTest(locked=bool(lock)):
                    (root / ".aidd" / "parent.toml").write_text(lock + parent, encoding="utf-8")
                    cfg = cfgmod.load_file(".aidd/config.toml", str(root))
                    self.assertEqual(cfg.get("project", "writing", "ste_100"), want)

    def test_config_md_documents_it_from_the_schema(self):
        self.assertIn("<!-- aidd:gen fields:config-project-writing -->", (ROOT / "docs" / "CONFIG.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
