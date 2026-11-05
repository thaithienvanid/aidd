"""What the release carries and says: the CI workflows (the eval key, template parity), the wheel's contents, the
installer's default before the first release, the release's changelog check, and the facts the public pages state
about routes, profiles, and the standards check."""

import os
import re
import shutil
import subprocess
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path

from helpers import IN_GIT_CHECKOUT, ROOT, repo_files

from aidd import config, pyz
from aidd.docsgen import schema_tables
from aidd.kernel import resources
from aidd.knowledge import team_registry

WORKFLOWS = ROOT / ".github" / "workflows"
TEMPLATES = ROOT / "templates" / "github"


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


class EvalKeyTests(unittest.TestCase):
    """A pull request's code never runs with the Anthropic API key: not from a fork, and not from this repository."""

    def setUp(self):
        self.text = (WORKFLOWS / "evals.yml").read_text(encoding="utf-8")

    def test_no_pull_request_gets_the_environment_or_the_key(self):
        env_line = next(line for line in self.text.splitlines() if line.strip().startswith("environment:"))
        self.assertIn("github.event_name != 'pull_request'", env_line)
        self.assertNotIn("head.repo.full_name", env_line)
        uses = [line for line in self.text.splitlines() if "secrets.ANTHROPIC_API_KEY" in line and not line.lstrip().startswith("#")]
        self.assertTrue(uses)
        for line in uses:
            self.assertIn("github.event_name != 'pull_request' &&", line, line)

    def test_every_live_step_waits_for_the_key(self):
        for step in self.text.split("\n      - ")[1:]:
            if "claude -p" in step or "claude plugin eval" in step:
                self.assertIn("if: env.HAS_KEY == 'true'", step, step.splitlines()[0])
        self.assertNotIn('"$GITHUB_EVENT_NAME" = pull_request', self.text)


def _blocks(text: str, key: str) -> list[str]:
    """Each `key:` block of a workflow, normalized: its inline value and the more-indented lines under it, without
    comments or blank lines."""
    lines = text.splitlines()
    out = []
    for i, line in enumerate(lines):
        m = re.match(rf"^(\s*){re.escape(key)}:(.*)$", line)
        if not m:
            continue
        indent = len(m.group(1))
        body = [m.group(2).split(" #", 1)[0].strip()]
        for nxt in lines[i + 1 :]:
            bare = nxt.split(" #", 1)[0].rstrip()
            if not bare.strip() or bare.lstrip().startswith("#"):
                continue
            if len(bare) - len(bare.lstrip()) <= indent:
                break
            body.append(bare.strip())
        out.append("\n".join(b for b in body if b))
    return out


class TemplateParityTests(unittest.TestCase):
    """The workflows this repository runs and the templates an adopter gets agree on every security-relevant line:
    the triggers, each job's permissions, and the secrets passed. Their steps may differ (this repository runs aidd from
    its own source, an adopter from the pinned release)."""

    def test_triggers_permissions_and_secrets_match(self):
        for name in ("aidd-tests.yml",):
            ours, theirs = (WORKFLOWS / name).read_text(encoding="utf-8"), (TEMPLATES / name).read_text(encoding="utf-8")
            for key in ("on", "permissions", "secrets", "concurrency"):
                with self.subTest(workflow=name, key=key):
                    self.assertEqual(_blocks(ours, key), _blocks(theirs, key))

    def test_every_pull_request_workflow_limits_its_concurrency(self):
        """A workflow a pull request starts declares a workflow-level concurrency group, and a trigger on a description
        edit gets a group of its own, so a run that does nothing never displaces one that would."""
        for path in (WORKFLOWS / "aidd-tests.yml", TEMPLATES / "aidd-tests.yml"):
            with self.subTest(path=path.name, dir=path.parent.name):
                text = path.read_text(encoding="utf-8")
                top = re.search(r"(?m)^concurrency:\n  group: (.+)\n  cancel-in-progress: (.+)$", text)
                self.assertIsNotNone(top)
                assert top is not None
                if "edited" in _blocks(text, "on")[0]:
                    self.assertIn("github.event.action == 'edited' && github.run_id", top.group(1))


class WheelContentsTests(unittest.TestCase):
    """The wheel maps its data folders in as sources, so .gitignore and the excludes apply: eval results and node_modules
    a maintainer made locally never ship. A force-include would copy each folder verbatim."""

    def setUp(self):
        self.wheel = tomllib.loads(read("pyproject.toml"))["tool"]["hatch"]["build"]["targets"]["wheel"]

    def test_the_data_folders_are_sources_with_excludes(self):
        self.assertNotIn("force-include", self.wheel)
        want = {"src/aidd": "aidd", **{rel: f"aidd/_data/{name}" for name, rel in resources._LAYOUT.items()}}
        self.assertEqual(self.wheel["sources"], want)
        self.assertEqual(sorted(self.wheel["only-include"]), sorted(want))
        for pattern in ("evals/results", "node_modules"):
            self.assertIn(pattern, self.wheel["exclude"])

    def test_the_zipapp_skips_the_same_output(self):
        self.assertEqual(pyz._SKIP("plugins/aidd-team", ["results", "node_modules", "skills"]), {"results", "node_modules"})

    # It builds a wheel with the hash-locked backend, so it runs where that is allowed: ci.yml's test job sets
    # BUILD_WHEEL_TEST=1 once uv is installed.
    @unittest.skipUnless(shutil.which("uv") and os.environ.get("BUILD_WHEEL_TEST") == "1", "set BUILD_WHEEL_TEST=1 with uv on PATH to build a wheel")
    def test_a_built_wheel_leaves_local_output_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "src-tree"
            work.mkdir()
            for rel in ("pyproject.toml", "README.md", "LICENSE", ".gitignore", "src", "schemas", "templates", ".agents/skills/aidd", "plugins/aidd-team"):
                src, dst = ROOT / rel, work / rel
                if src.is_dir():
                    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
                else:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
            for planted in ("plugins/aidd-team/evals/results/run.json", "plugins/aidd-team/node_modules/x/index.js"):
                (work / planted).parent.mkdir(parents=True, exist_ok=True)
                (work / planted).write_text("{}", encoding="utf-8")
            constraint = ROOT / ".github" / "requirements" / "build.txt"
            cmd = ["uv", "build", "--wheel", "-o", str(Path(tmp) / "dist"), "--build-constraint", str(constraint), "--require-hashes"]
            subprocess.run(cmd, cwd=work, check=True, capture_output=True, timeout=600)
            (whl,) = (Path(tmp) / "dist").glob("*.whl")
            names = zipfile.ZipFile(whl).namelist()
            self.assertFalse([n for n in names if "/evals/results/" in n or "/node_modules/" in n])
            self.assertIn("aidd/_data/team/.claude-plugin/plugin.json", names)
            self.assertIn("aidd/_data/team/tools/prototype/prototype.py", names)  # `aidd prototype` runs it from here
            self.assertIn("aidd/_data/skill/SKILL.md", names)


class SdistContentsTests(unittest.TestCase):
    """The sdist carries every tracked file, so its own tests run from it (ci.yml's build job), except the files named
    here as left out on purpose (none now)."""

    LEFT_OUT: set[str] = set()

    @unittest.skipUnless(IN_GIT_CHECKOUT, "compares the include list with the files version control tracks")
    def test_every_tracked_file_is_included_or_left_out_on_purpose(self):
        include = tomllib.loads(read("pyproject.toml"))["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
        dirs = tuple(p for p in include if p.endswith("/"))
        # hatchling adds these to every sdist whatever the include list says.
        always = {"pyproject.toml", ".gitignore"}
        missing = sorted(f for f in repo_files() if f not in include and not f.startswith(dirs) and f not in self.LEFT_OUT | always)
        self.assertEqual(missing, [])


class MissingReleaseTagTests(unittest.TestCase):
    """Before the first release, a template's `@vX.Y.Z` pin names a tag nobody can fetch: doctor says to pin a commit
    with --ref, and how to find one."""

    def test_doctor_names_ref_sha_for_a_tag_that_does_not_exist(self):
        from unittest import mock

        from helpers import git

        from aidd.setup import pins

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git(root, "init", "-q")
            git(root, "remote", "add", "origin", "https://github.com/example/app.git")
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "aidd-tests.yml").write_text("    uses: thaithienvanid/aidd@v1.0.0\n", encoding="utf-8")
            env = {k: v for k, v in os.environ.items() if k != "AIDD_OFFLINE"}
            with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(pins, "remote_refs", return_value={"refs/heads/main": "a" * 40}):
                (level, text), *_ = pins.pin_checks(root)
        self.assertEqual(level, "warn")
        self.assertIn("v1.0.0", text)
        self.assertIn("aidd upgrade --ref <sha> --yes", text)
        self.assertIn("aidd init --ref <sha>", text)
        self.assertIn(f"git ls-remote {pins.RELEASE_REPO_URL} refs/heads/main", text)


class ReleasePrivateRepositoryTests(unittest.TestCase):
    """Attestations need a public repository: the release's first step stops a private one before anything else runs,
    and RELEASING.md lists what the first public release needs."""

    def test_the_first_verify_step_refuses_a_private_repository(self):
        text = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
        verify = text.split("\n  verify:\n", 1)[1].split("\n  build:\n", 1)[0]
        steps = "\n".join(ln for ln in verify.split("\n    steps:\n", 1)[1].splitlines() if not ln.lstrip().startswith("#"))
        first = steps.split("\n      - ", 1)[0]
        self.assertIn("github.event.repository.private", first)
        self.assertIn("::error::", first)
        self.assertIn("exit 1", first)
        self.assertIn("public", first)

    def test_a_run_by_hand_is_a_dry_run_that_never_releases(self):
        text = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
        self.assertIn("\n  workflow_dispatch:\n", text.split("\npermissions:", 1)[0])
        release = text.split("\n  release:\n", 1)[1]
        self.assertIn("    if: github.event_name == 'push'", release.split("\n    steps:\n", 1)[0])
        verify = text.split("\n  verify:\n", 1)[1].split("\n  build:\n", 1)[0]
        for step in ("The tag matches", "The tag is annotated", "came through a pull request"):
            with self.subTest(step=step):
                self.assertIn("if: github.event_name == 'push'", verify.split(step, 1)[1].split("\n      - ", 1)[0])
        self.assertNotIn("if:", verify.split("The tagged commit is on main", 1)[1].split("\n      - ", 1)[0])

    def test_releasing_lists_what_the_first_public_release_needs(self):
        text = read("RELEASING.md")
        section = text.split("## The first public release", 1)[1].split("\n## ", 1)[0]
        for need in (
            "public",
            "CHANGELOG.md",
            "not on PyPI",
            "tag ruleset",
            "immutable releases",
            "Development Status :: 5 - Production/Stable",
        ):
            self.assertIn(need, section, need)

    def test_the_classifier_turns_stable_with_the_first_dated_release(self):
        classifiers = tomllib.loads(read("pyproject.toml"))["project"]["classifiers"]
        status = [c for c in classifiers if c.startswith("Development Status ::")]
        self.assertEqual(len(status), 1, status)
        released = re.search(r"(?m)^## \[?[1-9]\d*\.\d+\.\d+\]? (\(|- )\d{4}-\d{2}-\d{2}", read("CHANGELOG.md"))
        want = "Development Status :: 5 - Production/Stable" if released else "Development Status :: 4 - Beta"
        self.assertEqual(status[0], want)


class ReleaseRebuildTests(unittest.TestCase):
    """The release builds twice: a clean rebuild must match the build job's SHA256SUMS exactly before any attestation,
    so a release nobody can reproduce is never published."""

    def job(self, text: str, name: str) -> str:
        return text.split(f"\n  {name}:\n", 1)[1].split("\n\n  ", 1)[0]

    def test_a_clean_rebuild_gates_the_attestations(self):
        text = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
        build, rebuild = self.job(text, "build"), self.job(text, "rebuild")
        self.assertIn("needs: build", rebuild)
        self.assertIn("needs: [build, rebuild]", self.job(text, "attest"))
        self.assertIn("permissions:\n      contents: read\n    steps:", rebuild)  # least privilege: no write, no token
        for command in (
            'SOURCE_DATE_EPOCH=$(git log -1 --format=%ct "$GITHUB_SHA")',
            "uv build --no-cache --build-constraint .github/requirements/build.txt --require-hashes",
            "PYTHONPATH=src python -P -m aidd.pyz pyz/aidd.pyz",
            "version: 0.12.24",
            'python-version: "3.12"',
        ):
            self.assertIn(command, build, command)
            self.assertIn(command, rebuild, command)
        self.assertIn('diff -u meta/SHA256SUMS "$RUNNER_TEMP/SHA256SUMS.rebuild"', rebuild)
        self.assertIn("diffoscope", rebuild)  # the next step on a mismatch
        self.assertIn("exit 1", rebuild)
        for uses in re.findall(r"uses: (\S+)", rebuild):
            self.assertRegex(uses, r"@[0-9a-f]{40}$", uses)

    def test_the_ci_pipeline_practice_teaches_the_same_check(self):
        skill = ROOT / "plugins" / "aidd-team" / "skills" / "ci-pipeline"
        self.assertIn("(references/reproducible-builds.md)", (skill / "SKILL.md").read_text(encoding="utf-8"))
        ref = (skill / "references" / "reproducible-builds.md").read_text(encoding="utf-8")
        for words in (
            "SOURCE_DATE_EPOCH=$(git log -1 --format=%ct)",
            "two clean jobs",
            "sha256sum",
            "diffoscope",
            "network off",
            "-trimpath",
            "rewrite-timestamp=true",
            "project.build.outputTimestamp",
        ):
            self.assertIn(words, ref, words)


class ReleaseChangelogTests(unittest.TestCase):
    """The release refuses a version the changelog does not date, and accepts the heading RELEASING.md prescribes."""

    def pattern(self, version: str) -> re.Pattern:
        text = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
        line = next(ln for ln in text.splitlines() if ln.strip().startswith("pattern="))
        self.assertIn('pattern="^## \\[?${version//./\\\\.}\\]? (\\(|- )[0-9]{4}-[0-9]{2}-[0-9]{2}"', line)
        return re.compile(r"^## \[?" + re.escape(version) + r"\]? (\(|- )[0-9]{4}-[0-9]{2}-[0-9]{2}", re.M)

    def test_only_a_dated_entry_releases(self):
        p = self.pattern("1.0.0")
        self.assertRegex("## [1.0.0] - 2026-10-01\n", p)
        self.assertIn("`## [X.Y.Z] - YYYY-MM-DD`", read("RELEASING.md"))
        for undated in ("## [Unreleased]\n", "## [1.0.0]\n", "## [1.0.0] - Unreleased\n", "## [1.0.1] - 2026-10-01\n"):
            self.assertIsNone(p.search(undated), undated)

    def test_the_changelog_is_unreleased_or_dates_this_version(self):
        # Before its release, this version's entry reads `## [X.Y.Z] - Unreleased`; the release PR puts the date there.
        from aidd import __version__

        text = read("CHANGELOG.md")
        unreleased = "\n## [Unreleased]\n" in text or f"\n## [{__version__}] - Unreleased\n" in text
        self.assertTrue(unreleased or self.pattern(__version__).search(text))


class PublicFactsTests(unittest.TestCase):
    """What the public pages say matches what the code does."""

    def test_llms_txt_says_aidd_advises_and_enforces_nothing(self):
        first = read("llms.txt").split("\n\n", 2)[1]
        self.assertIn("advises", first)
        self.assertIn("enforces nothing", first)
        self.assertIn("ask", first)

    def test_the_profiles_table_names_when_each_profile_asks_for_spec_approval(self):
        table = schema_tables.profiles_table()
        solo = next(ln for ln in table.splitlines() if ln.startswith("| `solo` |"))
        team = next(ln for ln in table.splitlines() if ln.startswith("| `team` |"))
        self.assertTrue(solo.split("|")[3].strip() == "major", solo)
        self.assertTrue(team.split("|")[3].strip() == "normal, major", team)

    def test_route_lists_name_all_four_routes(self):
        method = read("docs/METHOD.md")
        skill = read(".agents/skills/aidd/SKILL.md").split("\n", 3)[2]
        self.assertEqual(config.ROUTE_KEYS, ("minor", "normal", "major", "emergency"))
        for route in config.ROUTE_KEYS:
            self.assertIn(f"`{route}`", method, route)
            self.assertRegex(skill, rf"\broute \([^)]*\b{route}\b", route)

    def test_every_copy_of_the_routing_sentence_keeps_its_clause(self):
        clause = "aidd advises the minimum from the paths it touches, and the author may declare higher"
        routing = f"A change's route is a property of the change. {clause}. The lane follows from the route."
        entry = team_registry.roles()["loop"]["entry"]
        self.assertTrue(entry.startswith(routing))
        texts = [f for f in repo_files() if f.endswith((".md", ".txt", ".json")) and not f.startswith("tests/")]
        files = [f for f in texts if "property of the change" in (ROOT / f).read_text(encoding="utf-8", errors="replace")]
        self.assertIn("docs/TEAM.md", files)
        for rel in files:
            text = read(rel)
            for m in re.finditer(r"property of the change", text):
                self.assertIn(clause, text[m.start() : m.start() + 400], f"{rel}: a copy of the routing sentence drifted")
        self.assertIn(routing, read("docs/TEAM.md"))

    def test_every_page_describing_the_standards_check_goes_past_the_age_check(self):
        team = read("docs/TEAM.md")
        checked = next(ln for ln in team.splitlines() if ln.startswith("- **Checked.** `aidd eval standards`"))
        # The age check is the review cadence (emerging 90 days, established a year, or the entry's own), not one year.
        for words in (
            "past its review cadence",
            "90 days",
            "`review_due`",
            "sharing one checked date",
            "moved",
            "no source to check",
            "an edition with no evidence",
            "license or no pin",
        ):
            self.assertIn(words, checked, words)
        for rel in ("docs/GLOSSARY.md",):
            line = next(ln for ln in read(rel).splitlines() if "`aidd eval standards` fails" in ln)
            said = line.split("`aidd eval standards` fails", 1)[1]
            self.assertRegex(said, r"source|evidence|confirm", rel)

    def test_no_page_says_a_standard_goes_stale_after_one_year(self):
        # An emerging entry is due after 90 days and an entry may set its own cadence or `review_due`: "a year" alone
        # tells a reader the wrong date for most of what the team watches closely.
        year = re.compile(r"(?i)(older than|more than|over) a year|within a year")
        texts = [f for f in repo_files() if f.endswith((".md", ".txt", ".json", ".py", ".yml", ".yaml")) and not f.startswith("tests/")]
        stale = [f"{rel}:{n}" for rel in texts for n, ln in enumerate(read(rel).splitlines(), 1) if year.search(ln) and re.search(r"(?i)standard|checked", ln)]
        self.assertEqual(stale, [])
        for rel in ("plugins/README.md", "plugins/aidd-team/skills/aidd-team/SKILL.md"):
            self.assertRegex(read(rel), r"emerging[^.]*90 days|90 days for an emerging", rel)


if __name__ == "__main__":
    unittest.main()
