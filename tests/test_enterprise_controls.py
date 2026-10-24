"""Compliance-ready and enterprise-ready by default: `[project.compliance]` and what it turns on.

Compliance is on when `targets` names a framework or the profile is audited: `aidd validate` then warns for a threat
model and an authorization matrix on security and auth paths, `aidd init` writes the security-scanning workflow, and
`aidd gate --paths` names the `enterprise-controls` pack. There is no level to set. `aidd record export --by-control` groups the evidence by control, `aidd
validate` warns on a postmortem action item past its due date, and a role writes the living docs of its own kinds."""

import contextlib
import io
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from helpers import ROOT, RepoTemplateCase, git, make_repo, run_cli
from test_linked_docs import spec_text

from aidd.guard import edit_check
from aidd.docsgen import pack_render
from aidd.tracking import record_export
from aidd.workitems import validation
from aidd.workitems import spec_warnings
from aidd.workitems import authoring
from aidd.setup import uninstalling
from aidd.setup import adoption as setup_adoption
from aidd.setup import config_template
from aidd import config as cfgmod
from aidd.config import project
from aidd.kernel import documents, json_schema, resources
from aidd.knowledge import team_registry

TEAM = ROOT / "plugins" / "aidd-team"
SKILL = ROOT / ".agents" / "skills" / "aidd"
PACK = TEAM / "skills" / "enterprise-controls"
HEAD = 'aidd_version: "1.0.0"\nprofile: "{profile}"\n\nowners:\n  approvers: ["@x"]\n'
TODAY = dt.date(2026, 9, 30)


def cfg(profile: str = "team", extra: str = "") -> cfgmod.Config:
    return cfgmod.load_text(HEAD.format(profile=profile) + extra)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


READY = "\nproject:\n  compliance:\n    targets: [soc2, gdpr]\n"


class ComplianceConfigTests(unittest.TestCase):
    """Item 1: the schema, when compliance is on, and a locked parent's floor."""

    def test_the_schema_takes_targets_and_no_level(self):
        prop = resources.load_json("config.schema.json")["properties"]["project"]["properties"]["compliance"]
        self.assertEqual(list(prop["properties"]), ["targets", "support_period"])
        self.assertEqual(set(prop["properties"]["targets"]["items"]["enum"]), {"soc2", "iso27001", "gdpr", "hipaa", "pci-dss", "fedramp", "cra", "other"})
        base = documents.parse_yaml(HEAD.format(profile="team"), "c")
        self.assertEqual(json_schema.validate(dict(base, project={"compliance": {"targets": ["soc2"]}}), "config.schema.json"), [])
        self.assertTrue(json_schema.validate(dict(base, project={"compliance": {"targets": ["soc2"], "level": "ready"}}), "config.schema.json"))
        self.assertTrue(json_schema.validate(dict(base, project={"compliance": {"targets": ["sox"]}}), "config.schema.json"))

    def test_on_with_a_target_or_under_the_audited_profile(self):
        self.assertEqual(project.project_compliance(cfg(extra=READY)), {"on": True, "targets": ["soc2", "gdpr"], "source": "targets"})
        self.assertEqual(project.project_compliance(cfg("audited")), {"on": True, "targets": [], "source": "profile"})
        self.assertEqual(project.project_compliance(cfg()), {"on": False, "targets": [], "source": "off"})
        self.assertFalse(project.project_compliance(None)["on"])
        self.assertFalse(hasattr(project, "COMPLIANCE_LEVELS"))
        self.assertFalse(hasattr(cfgmod, "COMPLIANCE_ON"))

    def test_a_locked_parent_keeps_its_targets(self):
        out = project.merge({"compliance": {"targets": ["soc2"]}}, {"compliance": {"targets": ["gdpr"]}}, locked=True, where="c", warnings=[])
        self.assertEqual(out["compliance"], {"targets": ["soc2", "gdpr"]})
        out = project.merge({"compliance": {"targets": ["soc2"]}}, {"compliance": {"targets": ["gdpr"]}}, locked=False, where="c", warnings=[])
        self.assertEqual(out["compliance"], {"targets": ["gdpr"]})

    def test_a_certification_target_under_solo_warns(self):
        for target in ("soc2", "iso27001", "pci-dss", "fedramp", "hipaa"):
            _, warnings = project.project_findings(cfg("solo", f'\nproject:\n  compliance:\n    targets: ["{target}"]\n'), TODAY)
            self.assertTrue(any("separation of duties" in w and target in w for w in warnings), (target, warnings))
        self.assertEqual(project.project_findings(cfg("solo", "\nproject:\n  compliance:\n    targets: [gdpr]\n"), TODAY), ([], []))
        self.assertEqual(project.project_findings(cfg("team", READY), TODAY), ([], []))

    def test_assess_names_the_pack(self):
        lines = "\n".join(project.project_markdown(project.effective_project(cfg(extra=READY))))
        self.assertIn("`aidd-team:enterprise-controls`", lines)
        self.assertIn("soc2", lines)
        self.assertIn("audited", "\n".join(project.project_markdown(project.effective_project(cfg("audited")))))
        self.assertNotIn("enterprise-controls", "\n".join(project.project_markdown(project.effective_project(cfg(extra="\nproject:\n  hosting: EU\n")))))
        # The owners and forecast JSON contracts carry it.
        p = project.effective_project(cfg(extra=READY))
        assert p is not None
        self.assertEqual(p["compliance"], {"targets": ["soc2", "gdpr"], "pack": "enterprise-controls"})
        self.assertNotIn("level", resources.load_json("owners.schema.json")["$defs"]["project"]["properties"]["compliance"]["properties"])


class InitTests(unittest.TestCase):
    """Items 1 and 4: init asks nothing, writes the commented targets, and the security CI only when compliance is on."""

    def init(self, root: Path, **kw) -> list[str]:
        kw.setdefault("approvers", ["@x"])
        return setup_adoption.init(
            root, setup_adoption.InitOptions(profile=kw.pop("profile", "team"), ci=kw.pop("ci", "github"), links=[], skill=False, harnesses=[], **kw)
        )

    def test_the_config_explains_the_targets_in_a_comment(self):
        text = config_template.config_text(config_template.ConfigTemplate("team", approvers=["@x"]))
        self.assertIn("# project:\n", text)
        self.assertIn("\n#   compliance:\n#     targets: [soc2, gdpr]\n", text)
        for word in ("soc2", "audited", "enterprise-controls"):
            self.assertIn(word, text)
        self.assertNotIn("level", text.split("#   compliance:", 1)[1])
        self.assertNotIn("compliance", documents.parse_yaml(text, "c").get("project", {}))
        text = config_template.config_text(config_template.ConfigTemplate("team", approvers=["@x"], compliance_targets=["soc2", "gdpr"]))
        self.assertEqual(documents.parse_yaml(text, "c")["project"]["compliance"], {"targets": ["soc2", "gdpr"]})
        self.assertEqual(cfgmod.load_text(text).warnings, [])

    def test_security_ci_only_when_compliance_is_on_or_when_asked(self):
        wf = Path(".github/workflows/aidd-security.yml")
        for kw, expected in (
            ({}, False),
            ({"compliance_targets": ["soc2"]}, True),
            ({"profile": "audited"}, True),
            ({"security_ci": True}, True),
        ):
            with self.subTest(**kw), tempfile.TemporaryDirectory() as d:
                self.init(Path(d), **kw)
                self.assertEqual((Path(d) / wf).is_file(), expected)
        with tempfile.TemporaryDirectory() as d:
            self.init(Path(d), ci="gitlab", security_ci=True)
            self.assertFalse((Path(d) / wf).exists())

    def test_gitlab_gets_the_secret_scan_under_the_same_condition(self):
        wf = Path(".gitlab/aidd-security.gitlab-ci.yml")
        for kw, expected in (
            ({}, False),
            ({"compliance_targets": ["soc2"]}, True),
            ({"profile": "audited"}, True),
            ({"security_ci": True}, True),
        ):
            with self.subTest(**kw), tempfile.TemporaryDirectory() as d:
                actions = self.init(Path(d), ci="gitlab", **kw)
                self.assertEqual((Path(d) / wf).is_file(), expected)
                self.assertEqual(any("`- local: .gitlab/aidd-security.gitlab-ci.yml`" in a for a in actions), expected, actions)
        with tempfile.TemporaryDirectory() as d:
            self.init(Path(d), ci="github", security_ci=True)
            self.assertFalse((Path(d) / wf).exists())
        with tempfile.TemporaryDirectory() as d:
            self.init(Path(d), ci="gitlab", security_ci=True)
            uninstalling.uninstall(Path(d), yes=True)
            self.assertFalse((Path(d) / wf).exists())

    def test_dependabot_is_written_with_the_stacks_it_finds(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "package.json").write_text('{"name": "x"}', encoding="utf-8")
            (Path(d) / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
            self.init(Path(d))
            text = read(Path(d) / ".github" / "dependabot.yml")
        self.assertIn("package-ecosystem: github-actions", text)
        self.assertIn("package-ecosystem: npm", text)
        self.assertIn("package-ecosystem: pip", text)
        self.assertIn("cooldown:", text)
        with tempfile.TemporaryDirectory() as d:
            self.init(Path(d), ci="none")
            self.assertFalse((Path(d) / ".github" / "dependabot.yml").exists())

    def test_the_cli_takes_the_flags_and_asks_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q", "-b", "main")
            code, out = run_cli(
                "init",
                d,
                "--profile",
                "team",
                "--approvers",
                "@x",
                "--compliance-target",
                "soc2",
                "--ci",
                "github",
                "--no-skill",
                "--harness",
                "none",
            )
            self.assertEqual(code, 0, out)
            data = documents.parse_yaml(read(Path(d) / ".aidd" / "config.yaml"), "c")
            self.assertEqual(data["project"]["compliance"], {"targets": ["soc2"]})
            self.assertTrue((Path(d) / ".github" / "workflows" / "aidd-security.yml").is_file())
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run_cli("init", "--compliance", "ready")


class SecurityWorkflowTests(unittest.TestCase):
    """Item 4: least privilege, pinned, no secret, and dependency audit, SAST, and an SBOM."""

    def setUp(self):
        self.text = read(ROOT / "templates" / "github" / "aidd-security.yml")

    def test_least_privilege_and_pinned(self):
        self.assertRegex(self.text, r"(?m)^permissions:\n  contents: read\n")
        self.assertNotRegex(self.text, r"(?m)^\s+[a-z-]+: write\b")
        self.assertNotIn("secrets.", self.text)
        uses = re.findall(r"(?m)^\s*-?\s*uses: (\S+)", self.text)
        self.assertTrue(uses)
        for u in uses:
            self.assertRegex(u, r"@[0-9a-f]{40}$", u)
        self.assertIn("persist-credentials: false", self.text)
        self.assertNotIn("pull_request_target", self.text)

    def test_it_scans_dependencies_code_and_writes_an_sbom(self):
        for word in ("osv-scanner", "semgrep==", "cyclonedx", "npm audit", "pip-audit", "govulncheck", "CodeQL"):
            self.assertIn(word, self.text)
        self.assertIn("jobs:\n  dependencies:", self.text)
        for job in ("sast:", "sbom:"):
            self.assertIn(f"\n  {job}", self.text)

    def test_dependabot_template(self):
        text = read(ROOT / "templates" / "github" / "dependabot.yml")
        self.assertIn("version: 2", text)
        self.assertIn("package-ecosystem: github-actions", text)


class SecretScanTests(unittest.TestCase):
    """EC-04: a secret scan over the history and the working tree, with gitleaks from its release, checksum-verified.

    The version is the one the enterprise-controls pack pins. The SHA-256 is the linux x64 tarball's line in that
    release's checksums file (https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_checksums.txt).
    On a pull or merge request the scan reads its config and ignore list from the base branch, so the change under
    scan cannot turn it off.
    """

    SHA256 = "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"
    EC04 = "the `secrets` job of `aidd-security.yml` (GitHub) or the `aidd-secrets` job of `aidd-security.gitlab-ci.yml` (GitLab)"
    FLAGS = 'set -- --config "$conf" --gitleaks-ignore-path "$ignore" --ignore-gitleaks-allow --no-banner --redact --verbose'

    @staticmethod
    def job(text: str, name: str) -> str:
        """One YAML job, from its key to the next key at the same indent."""
        indent = re.search(rf"(?m)^( *){re.escape(name)}:\s*$", text)
        assert indent, name
        rest = text[indent.end() :]
        end = re.search(rf"(?m)^{indent.group(1)}[\w.-]+:", rest)
        return rest[: end.start() if end else len(rest)]

    @staticmethod
    def scan_script(job: str) -> str:
        """The shell that runs the scan: the `run: |` block, or the GitLab script item, that unsets GITLEAKS_CONFIG."""
        blocks = re.findall(r"(?m)^( +)(?:run: \||- \|)\n((?:\1  .*\n|\s*\n)+)", job)
        found = [textwrap.dedent(body) for _, body in blocks if "unset GITLEAKS_CONFIG" in body]
        assert len(found) == 1, found
        return found[0]

    def setUp(self):
        pack = next(d for d in team_registry.roles()["domains"] if d["slug"] == "enterprise-controls")
        self.how = next(t["how"] for t in pack["tests"] if t["name"] == "Secret scan")
        self.version = re.search(r"gitleaks v(\d+\.\d+\.\d+)", self.how).group(1)
        self.jobs = {
            "github template": self.job(read(ROOT / "templates" / "github" / "aidd-security.yml"), "secrets"),
            "gitlab template": self.job(read(ROOT / "templates" / "gitlab" / "aidd-security.gitlab-ci.yml"), "aidd-secrets"),
            # Steps in the checks job: a pull request runs the checks and the tests only (test_action_shape.py).
            "aidd's own ci": self.job(read(ROOT / ".github" / "workflows" / "ci.yml"), "checks"),
        }

    def test_each_job_installs_the_pinned_release_and_checks_its_sha256(self):
        tarball = f"https://github.com/gitleaks/gitleaks/releases/download/v{self.version}/gitleaks_{self.version}_linux_x64.tar.gz"
        for where, job in self.jobs.items():
            with self.subTest(where=where):
                flat = job.replace("${GITLEAKS_VERSION}", self.version)
                self.assertRegex(job, rf"GITLEAKS_VERSION(: |=){re.escape(self.version)}\n")
                self.assertIn(tarball, flat)
                self.assertIn(self.SHA256, job)
                self.assertIn("sha256sum --check", job)

    def test_each_job_scans_the_history_and_the_tree_with_a_config_the_change_cannot_edit(self):
        for where, job in self.jobs.items():
            script = self.scan_script(job)
            with self.subTest(where=where):
                self.assertTrue(script.startswith("set -eu\n") or script.startswith("unset GITLEAKS_CONFIG GITLEAKS_CONFIG_TOML\n"), script)
                self.assertIn("unset GITLEAKS_CONFIG GITLEAKS_CONFIG_TOML\n", script)
                self.assertIn(self.FLAGS, script)
                self.assertRegex(script, r'gitleaks" git "\$@" \. \|\| status=1')
                self.assertRegex(script, r'gitleaks" dir "\$@" \. \|\| status=1')
                self.assertIn("rm -f .gitleaksignore\n", script)
                self.assertIn("printf '[extend]\\nuseDefault = true\\n' > \"$conf\"", script)
                self.assertIn(': > "$ignore"', script)
                # No gitleaks-action: it needs a license key in an organization.
                self.assertNotRegex(job, r"(?m)^\s*-?\s*uses: \S*gitleaks")
        self.assertEqual(self.scan_script(self.jobs["github template"]), self.scan_script(self.jobs["aidd's own ci"]))
        for where in ("github template", "aidd's own ci"):
            job = self.jobs[where]
            with self.subTest(where=where):
                self.assertIn("fetch-depth: 0", job)
                self.assertIn("BASE_REF: ${{ github.base_ref }}", job)
                # The full ref: a tag named origin/<base> cannot shadow the remote branch.
                self.assertIn('git show "refs/remotes/origin/$BASE_REF:.gitleaks.toml"', job)
                self.assertIn('git show "refs/remotes/origin/$BASE_REF:.gitleaksignore"', job)
                self.assertNotIn('"origin/$BASE_REF', job)
                # An expression only in `env:`, never inside a script.
                self.assertNotIn("${{", self.scan_script(job))
        gitlab = self.jobs["gitlab template"]
        self.assertIn("GIT_DEPTH: 0", gitlab)
        # The merge request's diff base by SHA, never the target branch by name: a fork's origin is the fork.
        self.assertNotIn("CI_MERGE_REQUEST_TARGET_BRANCH_NAME", gitlab)
        self.assertIn('git show "$base:.gitleaks.toml"', gitlab)
        self.assertIn('git show "$base:.gitleaksignore"', gitlab)
        # A fork controls a pipeline in its own project, so the scan belongs in the parent project's pipelines.
        for text in (read(ROOT / "templates" / "gitlab" / "aidd-security.gitlab-ci.yml"), read(ROOT / "docs" / "INSTALL.md")):
            self.assertIn("run pipelines in the parent project for merge requests from forks", text)

    def test_the_github_jobs_are_least_privilege_and_pinned(self):
        for where in ("github template", "aidd's own ci"):
            job = self.jobs[where]
            with self.subTest(where=where):
                self.assertNotRegex(job, r"(?m)^\s+[a-z-]+: write\b")
                self.assertNotIn("secrets.", job)
                self.assertIn("persist-credentials: false", job)
                uses = re.findall(r"(?m)^\s*-?\s*uses: (\S+)", job)
                self.assertTrue(uses)
                for u in uses:
                    self.assertRegex(u, r"@[0-9a-f]{40}$", u)
        self.assertNotRegex(read(ROOT / "templates" / "github" / "aidd-security.yml"), r"(?m)^\s*-?\s*uses: \S*gitleaks")
        self.assertNotIn("aidd-secrets", read(ROOT / "templates" / "gitlab" / "aidd.gitlab-ci.yml"))

    def test_ec04_names_the_job_on_both_platforms_in_one_form(self):
        self.assertIn(self.EC04, self.how)
        skill = read(ROOT / "plugins" / "aidd-team" / "skills" / "enterprise-controls" / "SKILL.md")
        controls = read(ROOT / "plugins" / "aidd-team" / "skills" / "enterprise-controls" / "references" / "controls.md")
        docs_controls = read(ROOT / "docs" / "CONTROLS.md")
        for where, text in (
            ("SKILL.md", skill),
            ("controls.md", controls),
            ("docs/CONTROLS.md", docs_controls),
            ("INSTALL.md", read(ROOT / "docs" / "INSTALL.md")),
        ):
            with self.subTest(where=where):
                self.assertIn(self.EC04, text)
        for where, text in (("controls.md", controls), ("docs/CONTROLS.md", docs_controls)):
            ec04 = next(line for line in text.splitlines() if line.startswith("| EC-04 "))
            self.assertIn(self.EC04, ec04, where)

    def test_install_says_how_to_allow_a_fake_key_and_what_push_protection_adds(self):
        text = read(ROOT / "docs" / "INSTALL.md")
        for words in ('condition = "AND"', "`.gitleaksignore`", "from the base branch", "push protection", "never scans the history"):
            self.assertIn(words, text)
        self.assertNotIn("push protection is an alternative", text)


@unittest.skipUnless(shutil.which("git") and shutil.which("sh"), "git and sh are required")
class SecretScanBehaviourTests(unittest.TestCase):
    """The scan scripts themselves, run with a stand-in gitleaks that records what it was given."""

    STUB = """#!/bin/sh
log="$(dirname "$0")/calls.log"
echo "ARGS $*" >> "$log"
while [ $# -gt 0 ]; do
  case "$1" in
    --config) echo "CONFIG $(cat "$2")" >> "$log"; shift ;;
    --gitleaks-ignore-path) echo "IGNORE [$(cat "$2")]" >> "$log"; shift ;;
    git|dir) mode="$1" ;;
  esac
  shift
done
[ -e .gitleaksignore ] && echo "TREE IGNORE" >> "$log"
echo "ENV [${GITLEAKS_CONFIG:-}${GITLEAKS_CONFIG_TOML:-}]" >> "$log"
[ "${STUB_FAIL:-}" = "$mode" ] && exit 1
exit 0
"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.upstream, self.work, self.temp = base / "upstream", base / "work", base / "temp"
        git(base, "init", "-q", "-b", "main", str(self.upstream))
        (self.upstream / "app.py").write_text("x = 1\n", encoding="utf-8")
        (self.upstream / ".gitleaks.toml").write_text("# base config\n", encoding="utf-8")
        git(self.upstream, "add", "-A")
        git(self.upstream, "commit", "-qm", "base")
        git(base, "clone", "-q", str(self.upstream), str(self.work))
        git(self.work, "checkout", "-q", "-b", "change")
        (self.work / ".gitleaks.toml").write_text('[allowlist]\npaths = [".*"]\n', encoding="utf-8")
        (self.work / ".gitleaksignore").write_text("a.txt:github-pat:1\n", encoding="utf-8")
        git(self.work, "add", "-A")
        git(self.work, "commit", "-qm", "change")
        stub = self.temp / "gitleaks" / "gitleaks"
        stub.parent.mkdir(parents=True)
        stub.write_text(self.STUB, encoding="utf-8")
        stub.chmod(0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def run_scan(self, platform: str, base: str | None, **env: str) -> tuple[int, str]:
        if platform == "github":
            script = SecretScanTests.scan_script(SecretScanTests.job(read(ROOT / "templates" / "github" / "aidd-security.yml"), "secrets"))
            env |= {"RUNNER_TEMP": str(self.temp), "BASE_REF": base or ""}
        else:
            job = SecretScanTests.job(read(ROOT / "templates" / "gitlab" / "aidd-security.gitlab-ci.yml"), "aidd-secrets")
            script = SecretScanTests.scan_script(job)
            # GitLab names the base by its SHA: "main" is the upstream's main; any other value is passed as it is.
            sha = git(self.upstream, "rev-parse", "main") if base == "main" else base
            env |= {"TMPDIR": str(self.temp)} | ({"CI_MERGE_REQUEST_DIFF_BASE_SHA": sha} if sha else {})
        full = {k: v for k, v in os.environ.items() if not k.startswith("CI_MERGE_REQUEST_")} | {"GITLEAKS_CONFIG": "/evil.toml"} | env
        run = subprocess.run(["sh", "-e", "-c", script], cwd=self.work, env=full, capture_output=True, text=True)
        log = self.temp / "gitleaks" / "calls.log"
        return run.returncode, log.read_text(encoding="utf-8") if log.exists() else run.stderr

    def test_a_pull_request_scans_with_the_base_branchs_files(self):
        for platform in ("github", "gitlab"):
            with self.subTest(platform=platform):
                code, log = self.run_scan(platform, "main")
                self.assertEqual(code, 0, log)
                self.assertEqual(log.count("CONFIG # base config"), 2, log)
                self.assertNotIn("paths", log)
                self.assertEqual(log.count("IGNORE []"), 2, log)
                self.assertNotIn("TREE IGNORE", log)
                self.assertEqual(log.count("ENV []"), 2, log)
                self.assertIn(" git ", log)
                self.assertIn(" dir ", log)
                self.assertFalse((self.work / ".gitleaksignore").exists())
                (self.temp / "gitleaks" / "calls.log").unlink()
                git(self.work, "checkout", "-q", "--", ".gitleaksignore")

    def test_a_tag_named_like_the_remote_branch_cannot_stand_in_for_it(self):
        git(self.work, "tag", "origin/main", "HEAD")  # the change's own commit, whose config allows every path
        code, log = self.run_scan("github", "main")
        self.assertEqual(code, 0, log)
        self.assertEqual(log.count("CONFIG # base config"), 2, log)
        self.assertNotIn("paths", log)

    def test_gitlab_fetches_a_diff_base_it_lacks_by_sha_and_else_fails_closed(self):
        (self.upstream / ".gitleaks.toml").write_text("# newer base config\n", encoding="utf-8")
        git(self.upstream, "commit", "-qam", "newer base")  # not in the work clone until fetched
        code, log = self.run_scan("gitlab", "main")
        self.assertEqual(code, 0, log)
        self.assertEqual(log.count("CONFIG # newer base config"), 2, log)
        (self.temp / "gitleaks" / "calls.log").unlink()
        git(self.work, "checkout", "-q", "--", ".gitleaksignore")
        for base in ("f" * 40, "HEAD", "change"):
            with self.subTest(base=base):
                code, log = self.run_scan("gitlab", base)
                self.assertEqual(code, 0, log)
                self.assertEqual(log.count("CONFIG [extend]\nuseDefault = true"), 2, log)
                self.assertEqual(log.count("IGNORE []"), 2, log)
                (self.temp / "gitleaks" / "calls.log").unlink()
                git(self.work, "checkout", "-q", "--", ".gitleaksignore")

    def test_a_base_without_a_config_gets_the_default_rules(self):
        git(self.upstream, "rm", "-q", ".gitleaks.toml")
        git(self.upstream, "commit", "-qm", "no config")
        git(self.work, "fetch", "-q", "origin")
        code, log = self.run_scan("github", "main")
        self.assertEqual(code, 0, log)
        self.assertEqual(log.count("CONFIG [extend]\nuseDefault = true"), 2, log)

    def test_a_push_uses_the_checked_out_tree(self):
        code, log = self.run_scan("github", None)
        self.assertEqual(code, 0, log)
        self.assertIn('paths = [".*"]', log)
        self.assertIn("IGNORE [a.txt:github-pat:1]", log)
        self.assertNotIn("TREE IGNORE", log)

    def test_a_finding_in_either_scan_fails_the_job_after_both_ran(self):
        for mode in ("git", "dir"):
            with self.subTest(mode=mode):
                code, log = self.run_scan("github", "main", STUB_FAIL=mode)
                self.assertEqual(code, 1, log)
                self.assertEqual(log.count("ARGS"), 2, log)
                (self.temp / "gitleaks" / "calls.log").unlink()


class RequiredDocsTests(unittest.TestCase):
    """Item 3: with compliance on, a threat model and an authz matrix are asked for on security and auth paths."""

    def asks(self, text: str, config: cfgmod.Config) -> dict[str, str]:
        data, _ = documents.split_front_matter(text)
        return {k: level for k, level, _ in authoring.required_docs(data, len(spec_warnings.acceptance_ids(text)), config)}

    def test_ready_warns_on_auth_and_secret_paths_without_a_security_dimension(self):
        auth = spec_text(scope='["src/auth/session.py"]')
        self.assertEqual(self.asks(auth, cfg(extra=READY)).get("threat-model"), "warn")
        self.assertEqual(self.asks(auth, cfg(extra=READY)).get("authz"), "warn")
        self.assertEqual(self.asks(auth, cfg("audited")).get("authz"), "warn")
        secrets = spec_text(scope='["src/crypto/keys.py"]')
        self.assertEqual(self.asks(secrets, cfg(extra=READY)).get("threat-model"), "warn")
        self.assertNotIn("authz", self.asks(secrets, cfg(extra=READY)))

    def test_compliance_off_and_other_paths_stay_quiet(self):
        auth = spec_text(scope='["src/auth/session.py"]')
        self.assertNotIn("threat-model", self.asks(auth, cfg()))
        self.assertNotIn("authz", self.asks(auth, cfg()))
        self.assertNotIn("threat-model", self.asks(spec_text(), cfg(extra=READY)))
        # The old triggers still hold whether compliance is on or off.
        self.assertEqual(self.asks(spec_text(dims='["security"]', scope='["src/auth/x.py"]'), cfg()).get("authz"), "warn")

    def test_the_condition_is_in_aidds_matrix(self):
        matrix = cfgmod.default_docs_required()
        self.assertIn({"compliance": True}, matrix["authz"]["any_of"])
        self.assertTrue(any(c.get("compliance") is True for c in matrix["threat-model"]["any_of"]))


class PostmortemActionTests(unittest.TestCase):
    """Item 3: problem management. An action item past its due date and not done is a warning."""

    PM = """---
aidd_version: "1.0.0"
kind: postmortem
id: PM-1
title: Checkout returned 500
incident_on: "2026-08-01"
severity: sev2
status: {status}

actions:
  - what: Alert on the error rate of checkout
    owner: "@alice"
    due: "2026-09-01"

  - what: Add the missing index
    owner: "@bob"
    due: "2026-09-02"
    done: true

  - what: Load test the new limiter
    owner: "@carol"
    due: "2026-12-01"
---

## Summary

Text.
"""

    def check(self, status: str) -> list[str]:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".aidd").mkdir()
            (root / ".aidd" / "config.yaml").write_text(HEAD.format(profile="team"), encoding="utf-8")
            (root / "docs" / "postmortems").mkdir(parents=True)
            (root / "docs" / "postmortems" / "PM-1.md").write_text(self.PM.format(status=status), encoding="utf-8")
            errors, warnings = validation.check_repo(root, TODAY)
        self.assertEqual(errors, [])
        return [w for w in warnings if "action" in w]

    def test_an_overdue_open_action_warns(self):
        found = self.check("published")
        self.assertEqual(len(found), 1, found)
        self.assertIn("Alert on the error rate", found[0])
        self.assertIn("@alice", found[0])
        self.assertIn("2026-09-01", found[0])

    def test_a_draft_is_still_being_written(self):
        self.assertEqual(self.check("draft"), [])

    def test_the_schema_and_template_carry_actions(self):
        props = resources.load_json("postmortem.schema.json")["properties"]["actions"]["items"]
        self.assertEqual(set(props["required"]), {"what", "owner", "due"})
        self.assertIn("done", props["properties"])
        self.assertIn("\nactions:\n  - what:", read(SKILL / "assets" / "postmortem.md"))  # YAML, as the front matter is


class ExportByControlTests(RepoTemplateCase):
    """Item 5: `aidd record export records --by-control` groups records and linked docs by the control ids in compliance docs."""

    COMPLIANCE = """# Compliance: audit log

Spec: [SPEC-7][spec].

## Obligations

| Control id | Obligation (law or standard, article) | Control | Evidence (test, file, or gate record) | Owner |
| --- | --- | --- | --- | --- |
| EC-15 | SOC 2 CC7.2 | Every admin action writes an audit event | A1 | @sec |
| EC-10, EC-15 | GDPR Art. 32 | Logs redact personal data | A2 | @sec |
| TODO | | | | |

[spec]: ../SPEC-7.md
"""

    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", branch=None)
        spec = spec_text(("compliance", "specs/SPEC-7/compliance-audit-log.md"), ("threat-model", "specs/SPEC-7/threat-model-audit-log.md"))
        (root / "specs").mkdir(exist_ok=True)
        (root / "specs" / "SPEC-7.md").write_text(spec.replace("id: SPEC-9", "id: SPEC-7"), encoding="utf-8")
        (root / "specs" / "SPEC-7").mkdir(parents=True)
        (root / "specs" / "SPEC-7" / "compliance-audit-log.md").write_text(cls.COMPLIANCE, encoding="utf-8")
        (root / "specs" / "SPEC-7" / "threat-model-audit-log.md").write_text("# Threat model SPEC-7\n", encoding="utf-8")
        rec = root / "records"
        rec.mkdir()
        base = {"aidd_version": "1.0.0", "decision": "pass", "failed_rules": [], "pending_rules": [], "route": "normal"}
        (rec / "a.json").write_text(json.dumps(base | {"change": "12", "head_sha": "a" * 40, "spec_id": "SPEC-7"}), encoding="utf-8")
        (rec / "b.json").write_text(json.dumps(base | {"change": "13", "head_sha": "b" * 40, "spec_id": "SPEC-8"}), encoding="utf-8")

    def test_records_and_docs_are_grouped_by_control(self):
        out = record_export.records_by_control(self.root, [str(self.root / "records")])
        self.assertEqual(json_schema.validate(out, "control-evidence.schema.json"), [])
        ids = [c["id"] for c in out["controls"]]
        self.assertEqual(ids, ["EC-10", "EC-15"])
        ec15 = out["controls"][1]
        self.assertEqual(len(ec15["obligations"]), 2)
        self.assertEqual(ec15["obligations"][0]["obligation"], "SOC 2 CC7.2")
        self.assertEqual(ec15["specs"], ["SPEC-7"])
        self.assertEqual([r["change"] for r in ec15["records"]], ["12"])
        self.assertIn({"spec": "SPEC-7", "kind": "threat-model", "path": "specs/SPEC-7/threat-model-audit-log.md"}, ec15["docs"])
        self.assertEqual(out["unmapped_records"], 1)

    def test_the_cli(self):
        with contextlib.chdir(self.root):
            code, text = run_cli("record", "export", "records", "records", "--by-control")
            self.assertEqual(code, 0, text)
            self.assertEqual(json.loads(text)["controls"][0]["id"], "EC-10")
            code, text = run_cli("record", "export", "events", "records", "--by-control")
            self.assertNotEqual(code, 0)
            code, text = run_cli("record", "export", "records", "records", "--by-control", "--format", "csv")
            self.assertNotEqual(code, 0)

    def test_the_template_has_the_column_and_the_format_is_documented(self):
        self.assertIn("| Control id |", read(SKILL / "assets" / "compliance.md"))
        self.assertIn("--by-control", read(ROOT / "docs" / "CONTROLS.md"))


@unittest.skipUnless(__import__("shutil").which("git"), "git is required")
class LivingDocGuardTests(RepoTemplateCase):
    """Item 8: a role writes the living docs of its own kinds; nothing else opens."""

    SLO, ACCEPTANCE = "specs/SPEC-220/slo-checkout.md", "specs/SPEC-220/acceptance-x.md"
    OUTSIDE = "docs/research/slo-other.md"

    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", spec="02-normal-feature:specs/SPEC-220.md")
        p = root / "specs" / "SPEC-220.md"
        entries = "\ndocs:\n" + "".join(
            f'  - kind: {k}\n    path: "{path}"\n    frozen: false\n' for k, path in (("slo", cls.SLO), ("acceptance", cls.ACCEPTANCE))
        )
        text = read(p).replace("scope: [src/checkout/rate_limit/]", f'scope: [src/checkout/rate_limit/, "{cls.SLO}", "{cls.ACCEPTANCE}"]', 1)
        p.write_text(text.replace("\ntests:", entries + "\ntests:", 1), encoding="utf-8")

    def decide(self, role, path):
        return edit_check.check_edit(str(self.root), path, role)[0]

    def test_each_role_writes_its_own_living_docs(self):
        self.assertEqual(self.decide("sre", self.SLO), "allow")
        self.assertEqual(self.decide("delivery-manager", self.ACCEPTANCE), "allow")

    def test_nothing_else_opens(self):
        self.assertEqual(self.decide("verifier", self.ACCEPTANCE), "deny")  # the SRE builds in the scope, so it may write any file there
        self.assertEqual(self.decide("product-manager", self.SLO), "deny")
        self.assertEqual(self.decide("product-manager", self.ACCEPTANCE), "deny")
        self.assertEqual(self.decide("sre", self.OUTSIDE), "deny")
        self.assertEqual(self.decide("security-engineer", self.SLO), "deny")


class PackTests(unittest.TestCase):
    """Item 2: the enterprise-controls pack, generated like every pack, with its control set in references."""

    def setUp(self):
        self.pack = next(d for d in team_registry.roles()["domains"] if d["slug"] == "enterprise-controls")
        self.controls = read(PACK / "references" / "controls.md")

    def test_it_is_a_generated_pack_that_points_to_its_references(self):
        text = read(PACK / "SKILL.md")
        self.assertEqual(text, pack_render.render_pack(self.pack))
        self.assertIn("references/controls.md", text)
        self.assertIn("`project.compliance`", text)
        head = json.loads(re.search(r"^description: (.+)$", text, re.M).group(1))
        self.assertTrue(head.startswith("In an aidd repository, use when code touches "))
        self.assertLessEqual(len(head), 200)
        for std in ("soc-2", "iso-iec-27001", "gdpr", "owasp-asvs"):
            self.assertIn(std, [s if isinstance(s, str) else s["id"] for s in self.pack["standards"]])

    def test_nineteen_controls_each_with_its_test_evidence_and_mappings(self):
        """One row per control (the reference stays under its 1,500-token cap): what the product must do, the test and
        evidence that prove it, and the SOC 2, ISO/IEC 27001, and GDPR items it serves; the per-step walk is one line."""
        rows = [r for r in self.controls.splitlines() if r.startswith("| EC-")]
        ids = [re.match(r"\| (EC-\d\d)", r).group(1) for r in rows]
        self.assertEqual(ids, [f"EC-{i:02d}" for i in range(1, 20)])
        self.assertIn("| Control | The product must | Test and evidence | Serves |", self.controls)
        for r in rows:
            with self.subTest(control=r[2:7]):
                cells = r.strip("|").split(" | ")
                self.assertEqual(len(cells), 4)
                for word in ("SOC 2", "ISO 27001", "GDPR"):
                    self.assertIn(word, cells[3])
        for step in ("Specify", "Implement", "Review", "Roll out"):
            self.assertIn(step, self.controls.split("\n| EC-19", 1)[1])

    def test_the_deal_checklist_and_the_ladder(self):
        text = self.controls + read(PACK / "references" / "readiness.md")
        for item in (
            "SSO",
            "OIDC",
            "SCIM",
            "MFA",
            "lockout",
            "session",
            "audit log",
            "admin console",
            "IP allowlisting",
            "data residency",
            "status page",
            "trust center",
            "security questionnaire",
            "VPAT",
        ):
            self.assertIn(item, text)
        for rung in ("MVP", "first paying", "first enterprise", "certification"):
            self.assertIn(rung, text.lower() if rung != "MVP" else text)
        self.assertIn("outside the team", text)

    def test_self_contained_and_no_invented_ids(self):
        for path in PACK.rglob("*.md"):
            for link in re.findall(r"\]\(([^)]+)\)", read(path)):
                self.assertFalse(link.startswith(("../", "/")), (path.name, link))
        # SOC 2 ids this pack could not check against a published text are marked.
        for sid in ("CC2.3", "CC9.2", "A1.3"):
            for line in self.controls.splitlines():
                if sid in line:
                    self.assertIn("unverified", line, line)


class PracticeAndGuidanceTests(unittest.TestCase):
    """Items 3, 6, 7, and the proposal checklist."""

    def test_asvs_level_1_is_the_default(self):
        self.assertIn("Level 1", read(TEAM / "skills" / "secure-coding" / "SKILL.md"))
        section = read(TEAM / "skills" / "aidd-team" / "references" / "roles.md").split("### security-engineer", 1)[1].split("\n### ", 1)[0]
        self.assertIn("Level 1", section)

    def test_access_management_lives_in_the_pack_and_secure_coding(self):
        self.assertFalse((TEAM / "skills" / "access-management").exists())
        # At most two references a pack, so access management (EC-16) is a section of readiness.md.
        self.assertFalse((PACK / "references" / "access.md").exists())
        text = read(PACK / "references" / "readiness.md").split("## Access management (EC-16)", 1)[1]
        for word in ("joiner", "mover", "leaver", "access review", "break-glass", "service account"):
            self.assertIn(word, text.lower())
        self.assertIn("references/readiness.md", read(PACK / "SKILL.md"))
        self.assertIn("least privilege", read(TEAM / "skills" / "secure-coding" / "SKILL.md").lower())
        self.assertIn("secure-coding", team_registry.roles()["roles"]["security-engineer"]["practices"])

    def test_breach_notification_clock(self):
        for path in (TEAM / "skills" / "incident-response" / "SKILL.md", SKILL / "references" / "emergency.md", SKILL / "assets" / "postmortem.md"):
            text = read(path)
            with self.subTest(path=path.name):
                self.assertIn("72 hours", text)
                self.assertIn("Art. 33", text)
                self.assertRegex(text, r"(?i)other (?:regimes|laws)")

    def test_the_proposal_asks_for_compliance_targets(self):
        text = read(TEAM / "skills" / "proposal" / "SKILL.md")
        self.assertIn("compliance targets", text)
        self.assertIn("`project.compliance`", text)


class DocsTests(unittest.TestCase):
    """Item 9."""

    def test_owner_pages(self):
        adoption = read(ROOT / "docs" / "ADOPTION.md")
        self.assertIn("## Compliance-ready by default", adoption)
        controls = read(ROOT / "docs" / "CONTROLS.md")
        self.assertIn("enterprise-controls", controls)
        self.assertIn("`project.compliance`", read(ROOT / "docs" / "TROUBLESHOOTING.md"))
        self.assertIn("enterprise-controls", read(ROOT / "CHANGELOG.md"))
        self.assertIn("compliance", read(ROOT / "docs" / "CONFIG.md"))


if __name__ == "__main__":
    unittest.main()
