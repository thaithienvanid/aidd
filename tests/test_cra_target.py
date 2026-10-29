"""The `cra` compliance target: the EU Cyber Resilience Act's vulnerability handling.

`cra` in `project.compliance.targets` turns compliance on like any target, and leans on EC-08 (scanning and an SBOM) and
EC-18 (vulnerability handling). It needs a declared `support_period`, which `aidd validate` asks for. `aidd new
vulnerability-policy` writes the repository's one policy (ISO/IEC 29147 and 30111), and `aidd doctor` warns when the
repository has no security.txt (RFC 9116) or its `Expires` is past or within 30 days.
"""

import contextlib
import datetime as dt
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, git, make_repo, run_cli

from aidd import config as cfgmod
from aidd.config import project
from aidd.kernel import documents, json_schema, resources
from aidd.setup import doctor_checks
from aidd.workitems import authoring, validation

HEAD = 'aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@x"]\n'
TODAY = dt.date(2026, 10, 22)
CRA = "\nproject:\n  compliance:\n    targets: [cra]\n"
PERIOD = '    support_period:\n      ends: "{ends}"\n'
ASSET = ROOT / ".agents" / "skills" / "aidd" / "assets" / "vulnerability-policy.md"
CONTROLS = ROOT / "plugins" / "aidd-team" / "skills" / "enterprise-controls" / "references" / "controls.md"


def cfg(extra: str = "") -> cfgmod.Config:
    return cfgmod.load_text(HEAD + extra)


def schema_errors(compliance: dict) -> list:
    return json_schema.validate({"aidd_version": "1.0.0", "profile": "team", "project": {"compliance": compliance}}, "config.schema.json")


@contextlib.contextmanager
def inside(root: Path):
    here = os.getcwd()
    os.chdir(root)
    try:
        yield
    finally:
        os.chdir(here)


class SchemaTests(unittest.TestCase):
    def test_cra_is_a_target_with_a_support_period_by_month(self):
        targets = resources.load_json("config.schema.json")["properties"]["project"]["properties"]["compliance"]["properties"]["targets"]
        self.assertIn("cra", targets["items"]["enum"])
        self.assertEqual(schema_errors({"targets": ["cra"], "support_period": {"ends": "2031-12"}}), [])
        self.assertEqual(schema_errors({"targets": ["cra"], "support_period": {"ends": "2028-06", "reason": "a two-year device"}}), [])
        for bad in ({"ends": "2031-13"}, {"ends": "2031-12-01"}, {"until": "2031-12"}, {"ends": "2031-12", "years": 5}):
            with self.subTest(bad=bad):
                self.assertTrue(schema_errors({"targets": ["cra"], "support_period": bad}))

    def test_cra_turns_compliance_on(self):
        self.assertEqual(project.project_compliance(cfg(CRA + PERIOD.format(ends="2031-12"))), {"on": True, "targets": ["cra"], "source": "targets"})

    def test_init_takes_the_target(self):
        cli = (ROOT / "docs" / "CLI.md").read_text(encoding="utf-8")
        self.assertIn("`--compliance-target soc2\\|iso27001\\|gdpr\\|hipaa\\|pci-dss\\|fedramp\\|cra\\|other`", cli)


class ValidateTests(unittest.TestCase):
    def test_cra_without_a_support_period_fails_and_names_the_fix(self):
        errors, warnings = project.project_findings(cfg(CRA), TODAY)
        self.assertEqual(
            errors,
            [
                "project.compliance targets cra with no support_period. The CRA makes you declare how long the product gets security "
                'updates (Art. 13(8)), at least five years. Add support_period: {ends: "YYYY-MM"} under project.compliance'
            ],
        )
        self.assertEqual(warnings, [])

    def test_a_support_period_that_ended_warns(self):
        errors, warnings = project.project_findings(cfg(CRA + PERIOD.format(ends="2026-09")), TODAY)
        self.assertEqual(errors, [])
        self.assertEqual(
            warnings,
            [
                "project.compliance.support_period ended in 2026-09, so the product gets no more security updates. A person sets a "
                "later end, or takes the product off the market"
            ],
        )

    def test_a_current_period_and_other_targets_are_quiet(self):
        self.assertEqual(project.project_findings(cfg(CRA + PERIOD.format(ends="2026-10")), TODAY), ([], []))  # this month still counts
        self.assertEqual(project.project_findings(cfg(CRA + PERIOD.format(ends="2031-12")), TODAY), ([], []))
        self.assertEqual(project.project_findings(cfg("\nproject:\n  compliance:\n    targets: [gdpr]\n"), TODAY), ([], []))

    def test_aidd_validate_reports_it(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / ".aidd" / "config.yaml"
            path.parent.mkdir()
            path.write_text(HEAD + CRA, encoding="utf-8")
            found = validation.validate_file(path, ".aidd/config.yaml")
        self.assertTrue(any(e.startswith(".aidd/config.yaml: project.compliance targets cra with no support_period") for e in found), found)

    def test_a_locked_parent_keeps_the_later_end(self):
        parent = {"compliance": {"targets": ["cra"], "support_period": {"ends": "2032-01"}}}
        child = {"compliance": {"support_period": {"ends": "2030-01"}}}
        locked = project.merge(parent, child, locked=True, where="c", warnings=[])
        self.assertEqual(locked["compliance"]["support_period"], {"ends": "2032-01"})
        longer = project.merge(parent, {"compliance": {"support_period": {"ends": "2034-01"}}}, locked=True, where="c", warnings=[])
        self.assertEqual(longer["compliance"]["support_period"], {"ends": "2034-01"})
        unlocked = project.merge(parent, child, locked=False, where="c", warnings=[])
        self.assertEqual(unlocked["compliance"]["support_period"], {"ends": "2030-01"})

    def test_init_writes_the_support_period_commented_for_a_person_to_declare(self):
        text = project.project_block(compliance=["cra"])
        self.assertIn('    # support_period:\n    #   ends: "YYYY-MM"', text)
        self.assertIn("cra", text.split("project:", 1)[0])
        data = documents.parse_yaml(text, "c")
        self.assertEqual(data["project"]["compliance"], {"targets": ["cra"]})
        self.assertNotIn("support_period:", project.project_block(compliance=["soc2"]))


class VulnerabilityPolicyTests(unittest.TestCase):
    def test_the_asset_covers_disclosure_handling_and_reporting(self):
        text = ASSET.read_text(encoding="utf-8")
        for words in (
            "ISO/IEC 29147",
            "ISO/IEC 30111",
            "RFC 9116",
            "Expires",
            "Contact",
            "CSAF 2.0 (ISO/IEC 20153:2025)",
            "OSV",
            "CycloneDX VEX",
            "Each week",
            "within 24 hours",
            "within 72 hours",
            "no later than 14 days",
            "support period",
            "`project.compliance.support_period.ends`",
            "`aidd-team:dependency-upgrade`",
            "`aidd-team:incident-response`",
            "security engineer",
        ):
            with self.subTest(words=words):
                self.assertIn(words, text)
        self.assertNotIn("48 hours", text)  # the fix windows have one owner: the dependency-upgrade skill

    def test_aidd_new_writes_the_repositorys_one(self):
        self.assertEqual(authoring.REPO_DOCS["vulnerability-policy"], (("{docs}/security/vulnerability-policy.md", "vulnerability-policy.md"),))
        with tempfile.TemporaryDirectory() as d, inside(Path(d)):
            git(d, "init", "-q")
            code, out = run_cli("new", "vulnerability-policy")
            self.assertEqual(code, 0, out)
            path = Path(d) / "docs" / "security" / "vulnerability-policy.md"
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("{{", text)
            self.assertIn("then: serve security.txt (RFC 9116) with Contact and Expires", out)
            code, out = run_cli("new", "vulnerability-policy")
            self.assertNotEqual(code, 0, "one per repository")
            self.assertIn("exists", out)
            code, out = run_cli("new", "vulnerability-policy", "--spec", "SPEC-1")
            self.assertNotEqual(code, 0, "the repository's, not a Spec's")

    def test_ec08_and_ec18_serve_the_cra(self):
        rows = {line.split(" | ")[0][2:7]: line for line in CONTROLS.read_text(encoding="utf-8").splitlines() if line.startswith("| EC-")}
        self.assertIn("CRA Annex I II(1)", rows["EC-08"])
        self.assertIn("CRA Annex I II, Art. 14", rows["EC-18"])
        self.assertIn("`aidd new vulnerability-policy`", rows["EC-18"])


def security_txt(expires: str | None) -> str:
    return "Contact: mailto:security@example.com\n" + (f"Expires: {expires}\n" if expires else "")


@unittest.skipUnless(shutil.which("git"), "git is required")
class DoctorTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        git(self.root, "init", "-q")
        self.cra = cfg(CRA + PERIOD.format(ends="2031-12"))

    def checks(self, config=None) -> list[tuple[str, str]]:
        return doctor_checks.security_txt_checks(self.root, config or self.cra, TODAY)

    def write(self, rel: str, text: str) -> None:
        (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.root / rel).write_text(text, encoding="utf-8")

    def test_no_security_txt_warns_and_names_the_policy(self):
        self.assertEqual(
            self.checks(),
            [
                (
                    "warn",
                    "project.compliance targets cra and the repository has no .well-known/security.txt. Add one (RFC 9116) with Contact and "
                    "Expires where the site serves it, as the vulnerability policy says (`aidd new vulnerability-policy`)",
                )
            ],
        )

    def test_an_expired_or_soon_expiring_file_warns(self):
        self.write(".well-known/security.txt", security_txt("2026-10-01T00:00:00Z"))
        ((level, message),) = self.checks()
        self.assertEqual(level, "warn")
        self.assertIn(".well-known/security.txt expired on 2026-10-01", message)
        self.write(".well-known/security.txt", security_txt("2026-11-21T00:00:00.000Z"))
        ((level, message),) = self.checks()
        self.assertEqual(level, "warn")
        self.assertIn("expires on 2026-11-21, in 30 days", message)

    def test_a_file_with_time_left_is_ok(self):
        self.write(".well-known/security.txt", security_txt("2027-06-30T00:00:00Z"))
        self.assertEqual(self.checks(), [("ok", ".well-known/security.txt: expires on 2027-06-30")])

    def test_no_readable_expires_warns(self):
        for text in (security_txt(None), security_txt("next year")):
            with self.subTest(text=text):
                self.write(".well-known/security.txt", text)
                ((level, message),) = self.checks()
                self.assertEqual(level, "warn")
                self.assertIn("has no readable Expires (RFC 9116 requires one", message)

    def test_it_finds_the_file_where_the_site_serves_it(self):
        self.write("public/.well-known/security.txt", security_txt("2026-10-30T00:00:00Z"))
        git(self.root, "add", "-A")
        ((level, message),) = self.checks()
        self.assertEqual(level, "warn")
        self.assertIn("public/.well-known/security.txt expires on 2026-10-30, in 8 days", message)

    def test_a_bom_and_a_lowercase_z_still_parse(self):
        (self.root / ".well-known").mkdir()
        (self.root / ".well-known" / "security.txt").write_bytes("﻿expires: 2027-06-30t00:00:00z\nContact: mailto:s@example.com\n".encode())
        self.assertEqual(self.checks(), [("ok", ".well-known/security.txt: expires on 2027-06-30")])

    def test_it_finds_the_file_under_a_folder_with_a_non_ascii_name(self):
        self.write("café/.well-known/security.txt", security_txt("2027-06-30T00:00:00Z"))
        git(self.root, "add", "-A")
        self.assertEqual(self.checks(), [("ok", "café/.well-known/security.txt: expires on 2027-06-30")])

    @unittest.skipIf(os.name == "nt", "symlinks and devices are POSIX here")
    def test_a_link_or_a_device_is_refused_never_read(self):
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        (outside / "security.txt").write_text(security_txt("2027-06-30T00:00:00Z"), encoding="utf-8")
        targets = [outside / "security.txt"] + [Path(p) for p in ("/dev/zero",) if os.path.exists(p)]
        for target in targets:
            with self.subTest(target=str(target)):
                link = self.root / ".well-known" / "security.txt"
                link.parent.mkdir(exist_ok=True)
                link.unlink(missing_ok=True)
                link.symlink_to(target)
                git(self.root, "add", "-A")
                ((level, message),) = self.checks()
                self.assertEqual(level, "warn")
                self.assertIn(".well-known/security.txt: it is a symlink or not a regular file, so aidd does not read it", message)
        if hasattr(os, "mkfifo"):
            link = self.root / ".well-known" / "security.txt"
            git(self.root, "rm", "-q", "--cached", "--", ".well-known/security.txt")
            link.unlink()
            os.mkfifo(link)  # a read of a pipe with no writer would wait for ever
            ((level, message),) = self.checks()
            self.assertIn("it is a symlink or not a regular file", message)

    def test_without_the_cra_target_it_is_quiet(self):
        self.assertEqual(self.checks(cfg("\nproject:\n  compliance:\n    targets: [soc2]\n")), [])
        self.assertEqual(doctor_checks.security_txt_checks(self.root, None, TODAY), [])

    def test_doctor_reports_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp).resolve() / "repo", branch=None)
            path = root / ".aidd" / "config.yaml"
            path.write_text(path.read_text(encoding="utf-8") + CRA + PERIOD.format(ends="2031-12"), encoding="utf-8")
            found = doctor_checks.doctor(root, today=TODAY)
            self.assertIn("warn", [level for level, m in found if "has no .well-known/security.txt" in m])
            self.assertFalse(any("security.txt" in m for _, m in doctor_checks.doctor(root, today=TODAY, failures_only=True)))


if __name__ == "__main__":
    unittest.main()
