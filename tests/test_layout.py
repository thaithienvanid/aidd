"""Where aidd writes (src/aidd/config/layout.py): a file directly in .aidd/ is committed, a folder in it is one
worktree's output that git ignores, and what every worktree shares lives in the git directory. No file still names an
older place: `aidd-evidence/` in the working tree, `.aidd/work/`, or `.aidd/preview/` (the preview sits in the
evidence folder)."""

import re
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts src on sys.path)
from helpers import repo_files

from aidd import config
from aidd.cli import parser

ROOT = Path(__file__).resolve().parent.parent
# CI stages the evidence in the runner's temporary folder, under the artifact's name; that is not the working tree.
CI_STAGING = re.compile(r"(\$RUNNER_TEMP|\$\{\{ runner\.temp \}\})/aidd-evidence/")


class LayoutTests(unittest.TestCase):
    def test_every_output_folder_is_a_folder_in_aidd(self):
        for rel in (config.EVIDENCE_DIR, config.VIEWS_DIR):
            self.assertEqual(Path(rel).parent, Path(".aidd"), rel)
        # The preview captures sit beside the evidence: artifacts.json names them relative to the evidence folder.
        self.assertEqual(Path(config.PREVIEW_DIR).parent, Path(config.EVIDENCE_DIR))
        self.assertEqual(config.OUTPUT_IGNORE, "/.aidd/*/")

    def test_the_commands_write_their_output_there(self):
        p = parser.build_parser()
        self.assertEqual(p.parse_args(["test"]).out, config.EVIDENCE_DIR)
        self.assertEqual(p.parse_args(["gate"]).evidence, f"{config.EVIDENCE_DIR}/evidence.json")
        self.assertEqual(p.parse_args(["record", "verify", "abc"]).dir, config.EVIDENCE_DIR)

    def test_no_file_names_an_older_place(self):
        tracked = repo_files()
        old = re.compile(r"(?<![\w$}/.-])aidd-evidence/|\.aidd/work\b|\.aidd/preview\b")
        found = []
        for rel in filter(None, tracked):
            path = ROOT / rel
            if path.suffix in {".png", ".jpg", ".gif", ".ico", ".pyz"} or not path.is_file() or rel == "tests/test_layout.py":
                continue
            text = CI_STAGING.sub("", path.read_text(encoding="utf-8", errors="replace"))
            found += [f"{rel}: {m.group(0)}" for m in old.finditer(text)]
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
