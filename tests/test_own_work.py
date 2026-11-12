"""Own work stays editable (V20): before Spec approval, each Specify role writes its own document first and files it
before sign-off, as a person does; `aidd validate` names what is not filed yet; after approval a new document is a
change to the Spec."""

import os
import shutil
import unittest
from unittest import mock

from helpers import RepoTemplateCase, make_repo

from aidd import config
from aidd.kernel import documents
from aidd.workitems import spec_warnings, validation

SPEC = "specs/SPEC-220.md"


@unittest.skipUnless(shutil.which("git"), "git is required")
class OwnWorkTests(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", spec=f"02-normal-feature:{SPEC}")

    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {k: v for k, v in os.environ.items() if k != "AIDD_SPEC"}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def unlinked(self) -> list[str]:
        data = documents.split_front_matter((self.root / SPEC).read_text(encoding="utf-8"), SPEC)[0]
        return validation.unlinked_in_folder(self.root, config.load_file(config.CONFIG_PATH, str(self.root)), data)

    def test_validate_names_a_document_in_the_specs_folder_that_it_does_not_link(self):
        doc = self.root / "specs" / "SPEC-220" / "adr-0001-limits.md"
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text("# ADR 1\n", encoding="utf-8")
        (self.root / "specs" / "SPEC-220" / "explore").mkdir()
        (self.root / "specs" / "SPEC-220" / "explore" / "notes.md").write_text("x\n", encoding="utf-8")  # explorations stay unlinked
        found = self.unlinked()
        self.assertEqual(len(found), 1, found)
        self.assertIn("specs/SPEC-220/adr-0001-limits.md sits in SPEC-220's folder, but the Spec does not link it", found[0])
        spec = self.root / SPEC
        spec.write_text(
            spec.read_text(encoding="utf-8").replace("\ntests:", "\ndocs:\n  - type: adr\n    path: specs/SPEC-220/adr-0001-limits.md\ntests:", 1),
            encoding="utf-8",
        )
        self.assertEqual(self.unlinked(), [])

    def test_validate_warns_on_a_spec_too_large_to_ship_and_on_a_refactor_inside_a_feature(self):
        from pathlib import Path

        data = {"change_type": "feat", "tasks": [{"id": f"T{i}", "title": f"build part {i}", "scope": ["src/x"]} for i in range(1, 8)]}
        data["tasks"][0]["title"] = "Rename the Problem schema to ProblemDetails"
        found = spec_warnings.size_warnings(Path(SPEC), "## Acceptance\n- A1: x\n", data)
        self.assertEqual(len(found), 2, found)
        self.assertIn("7 Tasks and 1 Acceptance items: likely too large", found[0])
        self.assertIn("task T1 (Rename the Problem schema to ProblemDetails) reshapes code inside a feature Spec", found[1])

    def test_validate_suggests_the_folder_for_a_scope_that_lists_its_files(self):
        from pathlib import Path

        files = ["src/billing/charge.py", "src/billing/refund.py", "src/billing/ledger.py"]
        data = {
            "change_type": "fix",
            "tasks": [{"id": "T1", "title": "refunds", "scope": files}, {"id": "T2", "title": "x", "scope": ["src/api/", "src/a.py"]}],
        }
        (found,) = spec_warnings.size_warnings(Path(SPEC), "## Acceptance\n- A1: x\n", data)
        self.assertIn("task T1 lists 3 files in src/billing/: scope the folder (`src/billing/`)", found)
        data["tasks"][0]["scope"] = files[:2]  # two files are a choice, not a habit
        self.assertEqual(spec_warnings.size_warnings(Path(SPEC), "## Acceptance\n- A1: x\n", data), [])


if __name__ == "__main__":
    unittest.main()
