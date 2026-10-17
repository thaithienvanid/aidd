"""Own work stays editable (V20): before Spec approval, each Specify role writes its own document first and files it
before sign-off, as a person does; `aidd validate` names what is not filed yet; after approval a new document is a
change to the Spec."""

import os
import shutil
import unittest
from unittest import mock

from helpers import RepoTemplateCase, git, make_repo

from aidd import config
from aidd.guard import edit_check, role_areas
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

    def decide(self, role, rel):
        return edit_check.check_edit(str(self.root), rel, role)

    def unlinked(self) -> list[str]:
        data = documents.split_front_matter((self.root / SPEC).read_text(encoding="utf-8"), SPEC)[0]
        return validation.unlinked_in_folder(self.root, config.load_file(config.CONFIG_PATH, str(self.root)), data)

    def test_each_specify_role_writes_its_own_document_before_it_files_it(self):
        own = {
            ("architect", "specs/SPEC-220/adr-0001-limits.md"): "link it from the Spec's `docs`",
            ("architect", "docs/adr/0001-limits.md"): "link it from the Spec's `docs`",
            ("security-engineer", "specs/SPEC-220/threat-model-limiter.md"): "link it from the Spec's `docs`",
            ("product-designer", "specs/SPEC-220/design/limits.html"): "list it in `design.files`",
            ("tester", "tests/checkout/test_burst.py"): "list it in `tests.files`",
        }
        for (role, rel), step in own.items():
            with self.subTest(role=role, rel=rel):
                decision, why = self.decide(role, rel)
                self.assertEqual(decision, "allow", why)
                self.assertIn(step, why)
        # Not their own kind: a role never writes another role's document, and implementation waits for approval.
        for role, rel in (("security-engineer", "specs/SPEC-220/adr-0001-limits.md"), ("tech-writer", "docs/guide.md"), ("developer", "src/other/x.py")):
            with self.subTest(role=role, rel=rel):
                self.assertEqual(self.decide(role, rel)[0], "deny")

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
            spec.read_text(encoding="utf-8").replace("\ntests:", "\ndocs:\n  - kind: adr\n    path: specs/SPEC-220/adr-0001-limits.md\ntests:", 1),
            encoding="utf-8",
        )
        self.assertEqual(self.unlinked(), [])

    def test_the_allowance_never_reaches_past_the_specs_own_new_work(self):
        cfg = config.load_file(config.CONFIG_PATH, str(self.root))
        # An id an agent wrote is never a glob: `*` would open every Spec's folder; nor one that is not the file's name.
        for sid, rel in (("*", "specs/SPEC-220.md"), ("SPEC-221", "specs/SPEC-220.md"), ("SPEC-2/../x", "specs/SPEC-2/../x.md")):
            self.assertEqual(role_areas.safe_draft_ids(cfg, [(rel, {"id": sid})], {sid}), [], sid)
        self.assertEqual(role_areas.safe_draft_ids(cfg, [("specs/SPEC-220.md", {"id": "SPEC-220"})], {"SPEC-220"}), ["SPEC-220"])
        # A test or an ADR the base already holds is another change's, never "your new file".
        for rel in ("tests/checkout/test_old.py", "docs/adr/0001-old.md"):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text("x\n", encoding="utf-8")
        git(self.root, "stash", "-q", "-u")
        git(self.root, "switch", "-q", "main")
        git(self.root, "stash", "pop", "-q")
        git(self.root, "add", "tests/checkout/test_old.py", "docs/adr/0001-old.md")
        git(self.root, "commit", "-qm", "older work on the base")
        git(self.root, "switch", "-q", "feat")
        git(self.root, "merge", "-q", "main")
        for role, rel in (("tester", "tests/checkout/test_old.py"), ("architect", "docs/adr/0001-old.md")):
            with self.subTest(role=role, rel=rel):
                self.assertEqual(self.decide(role, rel)[0], "deny")
        # A file another, approved Spec on the branch freezes is never paperwork.
        other = (self.root / SPEC).read_text(encoding="utf-8").replace("SPEC-220", "SPEC-221").replace("route: normal", 'route: normal\nstatus: "ready"', 1)
        other = other.replace("\ntests:", "\ndocs:\n  - kind: adr\n    path: docs/adr/0002-frozen.md\ntests:", 1)
        (self.root / "specs" / "SPEC-221.md").write_text(other, encoding="utf-8")
        self.assertEqual(self.decide("architect", "docs/adr/0002-frozen.md")[0], "deny")

    def test_validate_warns_on_a_spec_too_large_to_ship_and_on_a_refactor_inside_a_feature(self):
        from pathlib import Path

        data = {"type": "feat", "tasks": [{"id": f"T{i}", "title": f"build part {i}", "scope": ["src/x"]} for i in range(1, 8)]}
        data["tasks"][0]["title"] = "Rename the Problem schema to ProblemDetails"
        found = spec_warnings.size_warnings(Path(SPEC), "## Acceptance\n- A1: x\n", data)
        self.assertEqual(len(found), 2, found)
        self.assertIn("7 Tasks and 1 Acceptance items: likely over the change budget", found[0])
        self.assertIn("task T1 (Rename the Problem schema to ProblemDetails) reshapes code inside a feature Spec", found[1])

    def test_after_approval_a_new_document_is_a_change_to_the_spec(self):
        spec = self.root / SPEC
        spec.write_text(spec.read_text(encoding="utf-8").replace("route: normal", 'route: normal\nstatus: "ready"', 1), encoding="utf-8")
        for role, rel in (("architect", "specs/SPEC-220/adr-0002-later.md"), ("tester", "tests/checkout/test_burst.py")):
            with self.subTest(role=role, rel=rel):
                self.assertEqual(self.decide(role, rel)[0], "deny")


if __name__ == "__main__":
    unittest.main()
