"""What a fresh `aidd init` writes: a config with no warnings of its own, an approver list, and a pinned aidd reference."""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import git

from aidd.setup import doctor_checks
from aidd.workitems import validation
from aidd.setup import uninstalling
from aidd.setup import adoption
from aidd.setup import config_template
from aidd.setup import pins
from aidd.kernel import documents, resources


class ConfigTemplateTests(unittest.TestCase):
    def test_the_template_is_a_valid_config_with_a_modeline_and_no_schemas_folder(self):
        text = config_template.config_text(config_template.ConfigTemplate("team", approvers=["@org/leads"]))
        data = documents.parse_yaml(text, "config")
        self.assertEqual(data["owners"]["approvers"], ["@org/leads"])
        # An adopter's repository has no schemas folder: only the first line names one, aidd's own, by URL.
        self.assertTrue(text.startswith("# yaml-language-server: $schema=https://"), text[:120])
        self.assertNotIn("schemas/", text.split("\n", 1)[1])
        self.assertNotIn("default_owner_team", data.get("owners", {}))  # optional: `aidd new` writes a TODO without it

    def test_no_approvers_is_an_empty_list_that_means_whoever_directs_the_agent(self):
        text = config_template.config_text(config_template.ConfigTemplate("team"))
        self.assertEqual(documents.parse_yaml(text, "config")["owners"]["approvers"], [])
        self.assertIn("whoever directs", text)


SHA = "0123456789abcdef0123456789abcdef01234567"


class PinTests(unittest.TestCase):
    """`@v1.0.0` names a tag that does not exist yet and can move; init pins the CI files to a commit."""

    def test_every_aidd_reference_in_the_templates_is_pinned(self):
        tpl = resources.data_dir("templates")
        for rel in ("github/aidd-tests.yml", "github/aidd-standards.yml", "gitlab/aidd.gitlab-ci.yml"):
            text = (tpl / rel).read_text(encoding="utf-8")
            pinned = pins.pin_workflow(text, SHA)
            self.assertNotRegex(pinned, r"thaithienvanid/aidd[^\s\"]*@v\d", rel)
            self.assertIn(SHA, pinned, rel)
            if rel == "github/aidd-tests.yml":
                self.assertRegex(pinned, rf"uses: thaithienvanid/aidd\S*@{SHA} # aidd {SHA[:12]}\n", rel)
            elif rel.startswith("github/"):
                self.assertRegex(pinned, rf"repository: thaithienvanid/aidd\s+ref: {SHA}", rel)
            else:
                self.assertIn(f'aidd_pin="thaithienvanid/aidd@{SHA}"', pinned)
            self.assertEqual(pins.unpinned(pinned), pins.unpinned(text), rel)

    def test_a_ref_must_be_a_sha_or_a_release_tag(self):
        self.assertIn("@v1.2.3", pins.pin_workflow("uses: thaithienvanid/aidd@v1.0.0\n", "v1.2.3"))
        for bad in ("main; curl evil", "abc", "v1.0.0\nrun: x", "${{ github.sha }}"):
            with self.assertRaises(ValueError):
                pins.pin_workflow("uses: thaithienvanid/aidd@v1.0.0\n", bad)

    def test_init_writes_the_ref_and_uninstall_still_recognises_the_files(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            actions = adoption.init(root, adoption.InitOptions(profile="team", ci="github", links=[], skill=False, approvers=["@a"], harnesses=[], ref=SHA))
            self.assertIn(
                f"thaithienvanid/aidd@{SHA} # aidd {SHA[:12]}",
                (root / ".github/workflows/aidd-tests.yml").read_text(encoding="utf-8"),
            )
            self.assertTrue(any(SHA in a for a in actions))
            uninstalling.uninstall(root, yes=True)
            self.assertFalse((root / ".github/workflows/aidd-tests.yml").exists())
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            adoption.init(root, adoption.InitOptions(profile="team", ci="gitlab", links=[], skill=False, approvers=["@a"], harnesses=[], ref=SHA))
            self.assertIn(f'aidd_pin="thaithienvanid/aidd@{SHA}"', (root / ".gitlab/aidd.gitlab-ci.yml").read_text(encoding="utf-8"))
            uninstalling.uninstall(root, yes=True)
            self.assertFalse((root / ".gitlab/aidd.gitlab-ci.yml").exists())

    def test_from_a_checkout_the_default_is_the_running_commit(self):
        with mock.patch.object(pins, "installed_ref", return_value=SHA), tempfile.TemporaryDirectory() as d:
            adoption.init(Path(d), adoption.InitOptions(profile="team", ci="github", links=[], skill=False, approvers=["@a"], harnesses=[]))
            self.assertIn(f"thaithienvanid/aidd@{SHA} # aidd {SHA[:12]}", (Path(d) / ".github/workflows/aidd-tests.yml").read_text(encoding="utf-8"))
        with mock.patch.object(pins, "installed_ref", return_value=None), tempfile.TemporaryDirectory() as d:
            actions = adoption.init(Path(d), adoption.InitOptions(profile="team", ci="github", links=[], skill=False, approvers=["@a"], harnesses=[]))
            self.assertTrue(any(a.startswith("hint     pin the aidd workflow") for a in actions))


@unittest.skipUnless(shutil.which("git"), "git is required")
class FreshInitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q")

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_fresh_init_validates_without_warnings(self):
        adoption.init(
            self.root,
            adoption.InitOptions(
                profile="team", ci="github", links=[], approvers=["@org/leads"], specialists={"security": ["@org/sec"]}, test=["pytest"], harnesses=["codex"]
            ),
        )
        errors, warnings = validation.check_repo(self.root)
        self.assertEqual((errors, warnings), ([], []))
        report = doctor_checks.doctor(self.root)
        self.assertEqual([m for lvl, m in report if lvl == "fail"], [])
        self.assertEqual([m for lvl, m in report if lvl == "warn" and ("config" in m or "budget" in m or "approvers" in m)], [])

    def test_a_team_init_without_approvers_writes_an_empty_list_and_validates(self):
        adoption.init(self.root, adoption.InitOptions(profile="team", ci="none", links=[], harnesses=[], test=["pytest"]))
        self.assertEqual(documents.parse_yaml((self.root / ".aidd/config.yaml").read_text(encoding="utf-8"), "c")["owners"]["approvers"], [])
        self.assertEqual(validation.check_repo(self.root), ([], []))
        self.assertEqual([m for lvl, m in doctor_checks.doctor(self.root) if lvl == "fail"], [])


if __name__ == "__main__":
    unittest.main()
