"""One living threat model per component (V7): `aidd new threat-model <component>` writes it once under
docs/security/threat-models/, a later Spec links the same file again, and the gate and the guard treat a linked model as
documentation, never as implementation or a frozen file. A link elsewhere never widens a Spec's scope."""

import os
import shutil
import unittest
from pathlib import Path
from unittest import mock

from helpers import RepoTemplateCase, aidd_subprocess, git, make_repo

from aidd import gate, workitems
from aidd.evals import examples
from aidd.guard import edit_check
from aidd.kernel import documents

SPEC = "specs/SPEC-220.md"
MODEL = "docs/security/threat-models/checkout.md"


def living(path: str, frozen: bool = False) -> dict:
    return {"kind": "threat-model", "path": path, "frozen": frozen}


class ThreatModelPathsTests(unittest.TestCase):
    def test_only_a_living_model_in_its_home_counts(self):
        spec = {
            "docs": [
                living(MODEL),
                living("docs/security/threat-models/checkout.md", frozen=True),  # frozen: the Spec's own doc, not the component's
                living("src/checkout/app.py"),
                living("docs/security/threat-models/*.md"),
                living("docs/security/threat-models/../../../src/app.md"),
                living("docs/security/threat-models/nested/model.md"),
                {"kind": "slo", "path": "docs/security/threat-models/slo.md", "frozen": False},
            ]
        }
        self.assertEqual(workitems.threat_models(spec, "docs"), [MODEL])
        self.assertEqual(workitems.threat_models(spec, "documentation"), [])


class ThreatModelGateTests(unittest.TestCase):
    """The spec-phase case, with the component's model in the diff."""

    def run_gate(self, linked: str, changed: str):
        ctx, _ = examples.load_example(Path(__file__).resolve().parent.parent / "examples" / "16-spec-phase")
        spec = ctx["head_files"][SPEC]
        ctx["head_files"][SPEC] = spec.replace("tasks:\n", f"docs:\n  - kind: threat-model\n    path: {linked}\n    frozen: false\ntasks:\n", 1)
        ctx["files"].append({"path": changed, "previous_path": None, "additions": 30, "deletions": 0})
        ctx["head_tree"][changed] = "c" * 40
        return gate.decide(ctx)

    def test_the_linked_model_is_neither_scope_nor_implementation(self):
        result = self.run_gate(MODEL, MODEL)
        codes = [f["code"] for f in result.record["findings"]]
        self.assertNotIn("scope.outside", codes)
        self.assertEqual(result.record["phase"], "spec")

    def test_a_link_outside_the_models_folder_widens_nothing(self):
        for path in ("src/checkout/app.py", "docs/security/notes.md"):
            with self.subTest(path=path):
                codes = [f["code"] for f in self.run_gate(path, path).record["findings"]]
                self.assertIn("scope.outside", codes)


@unittest.skipUnless(shutil.which("git"), "git is required")
class ThreatModelRepoTests(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", spec=f"02-normal-feature:{SPEC}")
        other = (root / SPEC).read_text(encoding="utf-8").replace("id: SPEC-220", "id: SPEC-221").replace("trace_id: spec-220", "trace_id: spec-221")
        (root / "specs" / "SPEC-221.md").write_text(other, encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-qm", "spec: SPEC-221")

    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {k: v for k, v in os.environ.items() if k != "AIDD_SPEC"}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def new(self, *args):
        run = aidd_subprocess("new", *args, cwd=self.root)
        return run.returncode, run.stdout + run.stderr

    def docs(self, sid: str) -> list:
        return documents.split_front_matter((self.root / "specs" / f"{sid}.md").read_text(encoding="utf-8"))[0].get("docs") or []

    def test_a_second_spec_links_the_same_model(self):
        code, out = self.new("threat-model", "Checkout", "--spec", "SPEC-220")
        self.assertEqual(code, 0, out)
        self.assertIn("linked from", out)
        body = (self.root / MODEL).read_text(encoding="utf-8")
        self.assertIn("SPEC-220", body)
        code, out = self.new("threat-model", "checkout", "--spec", "SPEC-221")
        self.assertEqual(code, 0, out)
        self.assertIn("already has its threat model", out)
        self.assertEqual((self.root / MODEL).read_text(encoding="utf-8"), body)  # never rewritten
        for sid in ("SPEC-220", "SPEC-221"):
            self.assertEqual(self.docs(sid), [living(MODEL)])
        code, out = self.new("threat-model", "checkout", "--spec", "SPEC-221")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.docs("SPEC-221"), [living(MODEL)])  # linked once
        self.assertEqual(sorted(p.name for p in (self.root / "docs" / "security" / "threat-models").iterdir()), ["checkout.md"])

    def test_the_security_engineer_keeps_a_linked_model_current(self):
        self.assertEqual(self.new("threat-model", "checkout", "--spec", "SPEC-220")[0], 0)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "threat model: checkout")
        decision, why = edit_check.check_edit(str(self.root), MODEL, "security-engineer")
        self.assertEqual(decision, "allow", why)
        self.assertIn("living threat model", why)
        self.assertEqual(edit_check.check_edit(str(self.root), MODEL, "developer")[0], "deny")


if __name__ == "__main__":
    unittest.main()
