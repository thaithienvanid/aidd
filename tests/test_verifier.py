"""Config merging, validation of aidd files, credential scrubbing, templates, and the authoring edge cases."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, RepoTemplateCase, aidd_subprocess, make_repo

from aidd import config
from aidd.evals import suites
from aidd.workitems import validation
from aidd.workitems import authoring
from aidd.setup import adoption
from aidd.kernel import documents, json_schema

FEATURE = "02-normal-feature"
PY = sys.executable.replace("\\", "/")


def aidd(cwd, *args):
    return aidd_subprocess(*args, cwd=cwd)


class VerifierTests(unittest.TestCase):
    def test_approval_binding_is_gone(self):
        self.assertTrue(json_schema.validate({"aidd_version": "1.0.0", "profile": "team", "gates": {"approval_binding": "any"}}, "config.schema.json"))

    def test_config_suite_has_no_new_behavior(self):
        cfg = {"aidd_version": "1.0.0", "profile": "team", "tests": [{"name": "u", "command": ["t"], "new_behavior": True}]}
        self.assertTrue(json_schema.validate(cfg, "config.schema.json"))

    def test_parent_locks(self):
        parent = 'aidd_version: "1.0.0"\nprofile: team\nlocks: [tests]\ntests:\n  - {name: p, command: ["x"]}\n'
        child = 'aidd_version: "1.0.0"\nprofile: team\nextends: [{path: p.yaml}]\ntests:\n  - {name: c, command: ["y"]}\nowners:\n  approvers: ["@x"]\n'
        self.assertEqual([t["name"] for t in config.load_text(child, prefetched={"p.yaml": parent}).get("tests")], ["p"])
        self.assertEqual([t["name"] for t in config.load_text(child, prefetched={"p.yaml": parent.replace("locks: [tests]\n", "")}).get("tests")], ["c"])


@unittest.skipUnless(shutil.which("git"), "git is required")
class GitTests(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        make_repo(root, "solo", approvers=["@me"])

    def test_validate_directory_reads_only_aidd_files(self):
        (self.root / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
        self.assertEqual([e for e in validation.validate_file(self.root) if not e.startswith("warning")], [])


class CredentialScrubTests(unittest.TestCase):
    def test_credential_like_names_are_dropped(self):
        from aidd.kernel.processes import scrub_credentials

        env = {"PATH": "/bin", "DEPLOY_TOKEN": "x", "AWS_SECRET_ACCESS_KEY": "x", "DB_PASSWORD": "x", "GITHUB_TOKEN": "x", "SIGNING_KEY": "x", "LANG": "C"}
        self.assertEqual(sorted(scrub_credentials(env)), ["LANG", "PATH"])
        self.assertIn("DB_PASSWORD", scrub_credentials(env, keep=["DB_PASSWORD"]))
        self.assertNotIn("GITHUB_TOKEN", scrub_credentials(env, keep=["GITHUB_TOKEN"]))  # the platform tokens never pass


class TemplateTests(unittest.TestCase):
    def test_pr_template_block_is_commented_out(self):
        """A forgotten template must not declare a scope."""
        self.assertNotIn("```yaml aidd\nroute", (ROOT / ".github/pull_request_template.md").read_text(encoding="utf-8"))

    def test_version_test_reads_tracked_files_only(self):
        self.assertNotIn('"-co"', (ROOT / "tests/test_version.py").read_text(encoding="utf-8"))


class EdgeCaseTests(unittest.TestCase):
    """Edge cases of new objects, validation, outcome recording, scenarios, and the hook."""

    def test_new_spec_escapes_quotes_in_the_title(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "specs").mkdir()
            path = authoring.new_object(root, authoring.NewObject(item_type="spec", id="SPEC-1", title='Say "hi" \\ now', owner_team='a"b'))
            data, _ = documents.split_front_matter(path.read_text(encoding="utf-8"), str(path))
            self.assertEqual(data["title"], 'Say "hi" \\ now')
            self.assertEqual(data["owner_team"], 'a"b')

    def test_validate_reports_an_emergency_spec_without_review_due_instead_of_crashing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=[]))
            text = authoring.new_object(root, authoring.NewObject(item_type="spec", id="INC-1", title="Outage", route="emergency")).read_text(encoding="utf-8")
            self.assertIn("review_due:", text)
            text = text.replace("review_due:", "review_due_missing:", 1)
            (root / "specs" / "INC-1.md").write_text(text, encoding="utf-8")
            errors, _ = validation.check_repo(root)
            self.assertTrue(any("INC-1" in e for e in errors))

    def test_an_empty_scenario_list_loads_as_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.yaml").write_text("scenario: []\n", encoding="utf-8")
            self.assertEqual(suites.load_scenarios(Path(d)), [])


if __name__ == "__main__":
    unittest.main()
