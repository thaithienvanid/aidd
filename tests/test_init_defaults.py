"""What a fresh `aidd init` writes: a config with no warnings of its own, a named approver, and the gate's mode."""

import contextlib
import io
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import decide, example, git, package_source, source_of

from aidd.cli import app
from aidd.setup import doctor_checks
from aidd.workitems import validation
from aidd.setup import uninstalling
from aidd.setup import adoption
from aidd.setup import config_template
from aidd.setup import pins
from aidd import config
from aidd.config import identities
from aidd.kernel import documents, resources


class ConfigTemplateTests(unittest.TestCase):
    def test_the_template_names_no_catch_all_and_documents_policy_input(self):
        text = config_template.config_text(config_template.ConfigTemplate("team", approvers=["@org/leads"]))
        data = documents.parse_yaml(text, "config")
        self.assertIn("**/package-lock.json", data["budget_exclude_paths"])
        self.assertNotIn("**/*.lock", data["budget_exclude_paths"])  # it matches every lock file, so the rule treated it as a catch-all
        self.assertIn("AIDD_INPUT_FILE", text)
        self.assertNotIn("on stdin", text)
        self.assertIn("`unreachable`, which counts as deny", text)
        self.assertNotIn("schemas/", text)  # an adopter's repository has no schemas folder
        self.assertNotIn("default_team", data.get("owners", {}))  # optional: `aidd new` writes a TODO without it

    def test_an_unnamed_approver_fails_closed_and_says_so(self):
        text = config_template.config_text(config_template.ConfigTemplate("team"))
        self.assertEqual(documents.parse_yaml(text, "config")["owners"]["approvers"], [])
        self.assertIn("TODO: name who may approve", text)
        self.assertIn("email:you@example.com", text)  # local-first approvals name an email, as the skill's config does

    def test_the_mode_key_is_written_when_the_schema_has_it(self):
        with mock.patch.object(config_template, "config_supports_mode", return_value=True):
            self.assertEqual(
                documents.parse_yaml(config_template.config_text(config_template.ConfigTemplate("team", approvers=["@a"], mode="advisory")), "c")["mode"],
                "advisory",
            )
        with mock.patch.object(config_template, "config_supports_mode", return_value=False):
            text = config_template.config_text(config_template.ConfigTemplate("team", approvers=["@a"], mode="advisory"))
            self.assertNotIn("mode", documents.parse_yaml(text, "c"))
            self.assertIn("# mode: advisory", text)


SHA = "0123456789abcdef0123456789abcdef01234567"


class PinTests(unittest.TestCase):
    """`@v1.0.0` names a tag that does not exist yet and can move; init pins the CI files to a commit."""

    def test_every_aidd_reference_in_the_templates_is_pinned(self):
        tpl = resources.data_dir("templates")
        for rel in ("github/aidd-gate.yml", "github/aidd-tests.yml", "github/aidd-tests-central.yml", "gitlab/aidd.gitlab-ci.yml"):
            text = (tpl / rel).read_text(encoding="utf-8")
            pinned = pins.pin_workflow(text, SHA)
            self.assertNotRegex(pinned, r"thaithienvanid/aidd[^\s\"]*@v\d", rel)
            self.assertIn(SHA, pinned, rel)
            if rel.startswith("github/"):
                self.assertRegex(pinned, rf"uses: thaithienvanid/aidd\S*@{SHA} # aidd {SHA[:12]}\n", rel)
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
                f"thaithienvanid/aidd/.github/workflows/gate.yml@{SHA} # aidd {SHA[:12]}",
                (root / ".github/workflows/aidd-gate.yml").read_text(encoding="utf-8"),
            )
            self.assertTrue(any(SHA in a for a in actions))
            uninstalling.uninstall(root, yes=True)
            self.assertFalse((root / ".github/workflows/aidd-gate.yml").exists())
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
            self.assertTrue(any("--ref" in a for a in actions))


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

    def probe(self, code: str) -> tuple[str, ...]:
        """A login probe that runs `code` in Python and records that it ran, on any OS."""
        self.probes = getattr(self, "probes", 0) + 1
        marker = self.root.parent / f"probe-{self.probes}"
        return (sys.executable, "-c", f"open({str(marker)!r}, 'w', encoding='utf-8').close()\n{code}")

    def ran(self):
        return len(list(self.root.parent.glob("probe-*")))

    def test_solo_names_the_operator_from_local_config(self):
        probes = (self.probe("print('@octo-cat')"), self.probe("print('never asked')"))
        with mock.patch.object(identities, "LOGIN_PROBES", probes):
            actions = adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=[]))
        self.assertEqual(self.ran(), 1)  # the first probe answered, so the second never ran
        # The login for a platform's approvals, and the commit email a local approval counts as.
        self.assertEqual(
            documents.parse_yaml((self.root / ".aidd/config.yaml").read_text(encoding="utf-8"), "c")["owners"]["approvers"],
            ["@octo-cat", "email:tests@example.com"],
        )
        self.assertTrue(any("@octo-cat" in a for a in actions))

    def test_solo_without_a_login_leaves_a_todo_that_doctor_fails(self):
        probes = (self.probe("import sys; sys.exit(1)"), self.probe("print('not a login!')"))  # a failure, then a malformed answer
        no_email = self.probe("print('not an email')")
        with mock.patch.object(identities, "LOGIN_PROBES", probes), mock.patch.object(identities, "EMAIL_PROBE", no_email):
            adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=[]))
        self.assertEqual(self.ran(), 3)
        self.assertEqual(documents.parse_yaml((self.root / ".aidd/config.yaml").read_text(encoding="utf-8"), "c")["owners"]["approvers"], [])
        self.assertTrue(any(lvl == "fail" and "owners.approvers" in m for lvl, m in doctor_checks.doctor(self.root)))
        errors, _ = validation.check_repo(self.root)
        self.assertTrue(any("owners.approvers" in e for e in errors))

    def test_solo_without_a_login_names_the_commit_email(self):
        probes = (self.probe("import sys; sys.exit(1)"),)
        with mock.patch.object(identities, "LOGIN_PROBES", probes), mock.patch.object(identities, "EMAIL_PROBE", self.probe("print('me@example.com')")):
            actions = adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=[]))
        approvers = documents.parse_yaml((self.root / ".aidd/config.yaml").read_text(encoding="utf-8"), "c")["owners"]["approvers"]
        self.assertEqual(approvers, ["email:me@example.com"])
        self.assertTrue(any("email:me@example.com" in a for a in actions))

    def test_a_team_init_without_approvers_is_refused_unless_dry_run(self):
        for profile in ("team", "org", "audited"):
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                code = app.main(["init", str(self.root), "--profile", profile, "--ci", "none", "--harness", "none"])
            self.assertEqual(code, 2, profile)
            self.assertIn(f"aidd init --profile {profile} --approvers", err.getvalue())
            self.assertFalse((self.root / ".aidd").exists(), "a refused init writes nothing")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(app.main(["init", str(self.root), "--dry-run"]), 0)


class EmptyApproversWordingTests(unittest.TestCase):
    """The generated config, `aidd doctor`, `aidd validate`, and the gate say the same thing, and it is what the gate does."""

    def test_every_place_says_it_fails_closed(self):
        self.assertIn(config.EMPTY_APPROVERS, config_template.config_text(config_template.ConfigTemplate("team")))
        src = package_source("aidd.gate.rules")
        self.assertIn("no change can merge (the gate fails closed)", src)
        for text in (src, package_source("aidd.setup"), source_of("aidd.workitems.validation"), source_of("aidd.config")):
            self.assertNotIn("would let any account approve", text)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q")
            adoption.init(root, adoption.InitOptions(profile="team", ci="none", links=[], harnesses=[]))
            self.assertIn(("fail", "profile team needs owners.approvers; " + config.EMPTY_APPROVERS), doctor_checks.doctor(root))
            errors, _ = validation.check_repo(root)
            self.assertTrue(any(config.EMPTY_APPROVERS in e for e in errors), errors)

    def test_the_gate_fails_every_change_under_an_empty_list(self):
        ctx = example("01-minor-docs")
        ctx["base_config"] = re.sub(r"(?m)^  approvers: .*$", "  approvers: []", ctx["base_config"], count=1)
        d = decide(ctx)
        self.assertEqual(d.decision, "fail")
        self.assertIn("config.no_approvers", [f.code for f in d.findings])


if __name__ == "__main__":
    unittest.main()
