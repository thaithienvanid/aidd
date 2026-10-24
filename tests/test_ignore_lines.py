"""What tests and builds leave stays out of git, so the next `aidd test` runs in a clean tree.

`aidd test` counts an untracked file git does not ignore as a dirty tree, and the gate holds `tests.dirty_tree` on that
evidence. The control stays as it is: init and upgrade add each detected stack's outputs to .gitignore, under one
marked block that uninstall takes back alone, and the finding, the note, and doctor name the paths and the fix.
"""

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, decide, example, git, make_repo

from aidd.gate import rulebook
from aidd.setup import adoption, detection, doctor_checks, ignore_lines, uninstalling, upgrading

MARK = ignore_lines.TEST_OUTPUTS_MARK
OS = [ignore_lines.OS_FILES_MARK, *ignore_lines.OS_FILES]
# One manifest for each stack, as a repository holds it, and the stack `detection` names for it.
MANIFESTS = {
    "Python": ("pyproject.toml", "[project]\nname = 'x'\n"),
    "JavaScript/TypeScript": ("package.json", '{"name": "x"}\n'),
    "Rust": ("Cargo.toml", '[package]\nname = "x"\n'),
    "Go": ("go.mod", "module example.com/x\n"),
    "Java (Maven)": ("pom.xml", "<project></project>\n"),
    "JVM (Gradle)": ("build.gradle", "plugins { id 'java' }\n"),
    ".NET": ("App.csproj", "<Project></Project>\n"),
    "C/C++ (CMake)": ("CMakeLists.txt", "cmake_minimum_required(VERSION 3.20)\nproject(x CXX)\n"),
    "Dart/Flutter": ("pubspec.yaml", "name: x\n"),
}


@unittest.skipUnless(shutil.which("git"), "git is required")
class TestOutputLinesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        git(self.root, "init", "-q")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel: str, text: str = "") -> None:
        (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.root / rel).write_text(text, encoding="utf-8")

    def missing(self, gitignore: str = "") -> list[str]:
        if gitignore:
            self.write(".gitignore", gitignore)
        return ignore_lines.missing_ignore_lines(self.root, gitignore, detection.stack_names(self.root))

    def test_each_stack_is_detected_and_gets_its_own_outputs(self):
        self.assertEqual(set(MANIFESTS), set(ignore_lines.OUTPUTS), "a stack with outputs and no manifest here goes untested")
        for stack, (name, text) in MANIFESTS.items():
            with self.subTest(stack), tempfile.TemporaryDirectory() as d:
                root = Path(d).resolve()
                git(root, "init", "-q")
                (root / name).write_text(text, encoding="utf-8")
                self.assertEqual(detection.stack_names(root), [stack])
                self.assertEqual(ignore_lines.missing_ignore_lines(root, "", [stack]), [MARK, *ignore_lines.OUTPUTS[stack], *OS])

    def test_a_cmake_file_without_a_project_is_no_stack(self):
        self.write("lib/CMakeLists.txt", "add_library(x x.cc)\n")
        self.assertEqual(detection.stack_names(self.root), [])

    def test_what_git_already_ignores_is_never_added(self):
        self.write(*MANIFESTS["Python"])
        self.write(*MANIFESTS["Rust"])
        mine = "**/__pycache__\n*.py[cod]\n.pytest_cache\n/.coverage\nhtmlcov\n.mypy_cache/\n.ruff_cache/\n/target\n"
        self.assertEqual(self.missing(mine), OS)
        self.assertEqual(self.missing("/target\n__pycache__/\n"), [MARK, *ignore_lines.OUTPUTS["Python"][1:], *OS])

    def test_an_output_the_project_commits_is_never_added(self):
        self.write(*MANIFESTS[".NET"])
        self.write("bin/release.sh", "echo hi\n")
        git(self.root, "add", "-A")
        self.assertEqual(self.missing(), [MARK, "obj/", "TestResults/", *OS])

    def test_the_persons_global_excludes_file_does_not_count(self):
        """A teammate's clone and CI never read this machine's excludes file, so the repository needs the line."""
        self.write(*MANIFESTS["Rust"])
        excludes = self.root.parent / f"{self.root.name}-excludes"
        excludes.write_text("target/\n", encoding="utf-8")
        self.addCleanup(excludes.unlink)
        git(self.root, "config", "core.excludesFile", str(excludes))
        self.assertEqual(self.missing(), [MARK, "target/", *OS])

    def test_this_clones_info_exclude_does_not_count(self):
        """`.git/info/exclude` lives in one clone, so CI never reads it: a line only it covers is still added, and a
        .gitignore line that also covers one still counts, as does a .gitignore negation."""
        self.write(*MANIFESTS["JavaScript/TypeScript"])
        info_exclude = Path(git(self.root, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude"))
        info_exclude.parent.mkdir(parents=True, exist_ok=True)
        info_exclude.write_text("node_modules/\ncoverage/\n.nyc_output/\n", encoding="utf-8")
        self.assertEqual(self.missing(), [MARK, *ignore_lines.OUTPUTS["JavaScript/TypeScript"], *OS])
        self.assertEqual(
            self.missing("coverage/\ntest-results/\n!test-results/\n"), [MARK, "node_modules/", ".nyc_output/", "test-results/", "playwright-report/", *OS]
        )

    def test_outside_git_the_gitignore_lines_answer(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
            self.assertEqual(ignore_lines.missing_ignore_lines(root, "__pycache__/\n*.py[cod]\n", ["Python"]), [MARK, *ignore_lines.OUTPUTS["Python"][2:], *OS])

    def test_the_block_is_written_once_so_a_line_a_person_deleted_stays_deleted(self):
        self.write(*MANIFESTS["Go"])
        self.assertEqual(self.missing(f"{MARK}\ncoverage.out\n"), OS)
        self.assertEqual(self.missing(f"{MARK}\ncoverage.out\n{OS[0]}\n"), [])

    def test_a_python_script_with_no_manifest_still_counts_and_a_repository_without_a_stack_gets_the_os_files(self):
        self.write("tool.py", "print(1)\n")
        self.assertEqual(self.missing(), OS)  # untracked: not yet the project's
        git(self.root, "add", "tool.py")
        self.assertEqual(self.missing(), [MARK, *ignore_lines.OUTPUTS["Python"], *OS])

    def test_an_os_file_the_global_excludes_hide_is_still_added_and_one_the_project_commits_is_not(self):
        excludes = self.root.parent / f"{self.root.name}-excludes"
        excludes.write_text(".DS_Store\n", encoding="utf-8")
        self.addCleanup(excludes.unlink)
        git(self.root, "config", "core.excludesFile", str(excludes))
        self.write("assets/Thumbs.db", "x")
        git(self.root, "add", "-A")
        self.assertEqual(self.missing(), [ignore_lines.OS_FILES_MARK, ".DS_Store", "desktop.ini"])

    def test_troubleshooting_lists_each_output_ignore_lines_owns(self):
        text = (ROOT / "docs" / "TROUBLESHOOTING.md").read_text(encoding="utf-8")
        section = text.split("### `tests.dirty_tree`", 1)[1].split("\n### ", 1)[0]
        listed = {line for row in re.findall(r"^\| [^|]+ \| (.+) \|$", section, re.M)[1:] for line in re.findall(r"`([^`]+)`", row)}
        self.assertEqual(listed, set(ignore_lines.KNOWN))
        self.assertIn(MARK.split(", so")[0], section)

    def test_the_old_bytecode_block_keeps_its_lines_and_the_new_block_adds_the_rest(self):
        self.write(*MANIFESTS["Python"])
        old = f"{ignore_lines.BYTECODE_MARK}\n__pycache__/\n*.pyc\n"
        self.assertEqual(self.missing(old), [MARK, *ignore_lines.OUTPUTS["Python"][2:], *OS])


@unittest.skipUnless(shutil.which("git"), "git is required")
class InitUpgradeUninstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        git(self.root, "init", "-q")

    def tearDown(self):
        self.tmp.cleanup()

    def init(self) -> list[str]:
        return adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], approvers=["@a"], harnesses=[], ref="v1.0.0"))

    def gitignore(self) -> str:
        return (self.root / ".gitignore").read_text(encoding="utf-8")

    def test_init_appends_the_block_says_why_and_the_dry_run_lists_it(self):
        (self.root / "package.json").write_text('{"name": "x"}\n', encoding="utf-8")
        (self.root / ".gitignore").write_text("node_modules\n", encoding="utf-8")
        dry = detection.detection_markdown(detection.detect(self.root))
        self.assertIn("`aidd init` adds lines to `.gitignore`, so what tests, builds, and your computer leave stays out of git", dry)
        self.assertIn("`coverage/`", dry)
        out = self.init()
        self.assertTrue(self.gitignore().startswith("node_modules\n"), "a person's lines stay as they are")
        self.assertIn(f"{MARK}\ncoverage/\n.nyc_output/\ntest-results/\nplaywright-report/\n", self.gitignore())
        self.assertNotIn("node_modules/", self.gitignore())
        (said,) = [a for a in out if ".gitignore" in a]
        self.assertIn("because `aidd test` counts an untracked file as a dirty tree: `coverage/`", said)

    def test_uninstall_takes_back_only_aidds_block(self):
        (self.root / "Cargo.toml").write_text('[package]\nname = "x"\n', encoding="utf-8")
        (self.root / ".gitignore").write_text("build/\n", encoding="utf-8")
        self.init()
        with open(self.root / ".gitignore", "a", encoding="utf-8") as fh:
            fh.write("\n# mine\ntarget/\n")
        self.assertIn(f"{MARK}\ntarget/\n", self.gitignore())
        uninstalling.uninstall(self.root, yes=True)
        self.assertEqual(self.gitignore(), "build/\n\n# mine\ntarget/\n")

    def test_uninstall_takes_back_the_old_bytecode_block_too(self):
        (self.root / ".gitignore").write_text(f"dist/\n{ignore_lines.BYTECODE_MARK}\n__pycache__/\n*.pyc\n", encoding="utf-8")
        uninstalling.uninstall(self.root, yes=True)
        self.assertEqual(self.gitignore(), "dist/\n")

    def test_upgrade_lists_the_block_in_a_dry_run_and_appends_it_with_yes(self):
        self.init()
        (self.root / "go.mod").write_text("module example.com/x\n", encoding="utf-8")
        before = self.gitignore()
        dry = upgrading.upgrade(self.root, ref="v1.0.0")
        self.assertTrue(any(a.startswith("would update") and "`coverage.out`" in a and "`*.test`" in a for a in dry), dry)
        self.assertEqual(self.gitignore(), before)
        upgrading.upgrade(self.root, ref="v1.0.0", yes=True)
        self.assertEqual(self.gitignore(), before + f"{MARK}\ncoverage.out\n*.test\n")
        self.assertFalse(any(".gitignore" in a for a in upgrading.upgrade(self.root, ref="v1.0.0")))


FIX = rulebook.BY_NAME["tests"].fix_for("tests.dirty_tree")


class DirtyTreeNamesThePathsTests(unittest.TestCase):
    def test_the_fix_says_what_to_ignore_what_to_commit_and_what_to_run(self):
        self.assertIn("to .gitignore", FIX)
        self.assertIn("commit or stash your own changes", FIX)
        self.assertTrue(FIX.endswith("then run `aidd test` again"))

    def test_the_gate_finding_names_the_first_paths_and_the_fix(self):
        ctx = example("02-normal-feature")
        paths = [f"coverage/{i}.json" for i in range(7)]
        ctx["evidence"] |= {"dirty_tree": True, "dirty_paths": paths}
        (finding,) = [f for f in decide(ctx).findings if f.code == "tests.dirty_tree"]
        self.assertIn(", ".join(paths[:5]) + ", and more", finding.message)
        self.assertNotIn(paths[5], finding.message)
        self.assertEqual(finding.fix, FIX)
        again = example("02-normal-feature")
        again["evidence"] |= {"dirty_tree": True, "dirty_paths": paths}
        self.assertEqual([f.message for f in decide(again).findings], [f.message for f in decide(ctx).findings], "deterministic")


@unittest.skipUnless(shutil.which("git"), "git is required")
class DoctorDirtyEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_repo(Path(self.tmp.name).resolve() / "repo", "solo")
        self.head = git(self.root, "rev-parse", "HEAD")

    def tearDown(self):
        self.tmp.cleanup()

    def evidence(self, **fields) -> None:
        out = self.root / ".aidd" / "evidence"
        out.mkdir(parents=True, exist_ok=True)
        (out / "evidence.json").write_text(json.dumps({"head_sha": self.head, "base_sha": self.head, "results": [], **fields}), encoding="utf-8")

    def test_doctor_warns_with_the_paths_and_the_fix(self):
        self.evidence(dirty_tree=True, dirty_paths=[".pytest_cache/v/x", "htmlcov/index.html"])
        warned = [m for level, m in doctor_checks.doctor(self.root) if level == "warn" and "dirty tree" in m]
        self.assertEqual(
            warned,
            [f"the latest `aidd test` here ran in a dirty tree (.pytest_cache/v/x, htmlcov/index.html), so the gate holds it as tests.dirty_tree: {FIX}"],
        )
        git(self.root, "commit", "-q", "--allow-empty", "-m", "later")
        self.assertTrue(doctor_checks.dirty_evidence_lines(self.root), "still this branch's latest run")

    def test_doctor_reads_the_paths_as_text_from_a_file(self):
        """The paths come from a file anything could write: a value that is no list of text names none, and a control
        character never reaches the terminal."""
        for paths in (5, "abc", [1, "x"], {"a": 1}):
            with self.subTest(paths=paths):
                self.evidence(dirty_tree=True, dirty_paths=paths)
                (line,) = doctor_checks.dirty_evidence_lines(self.root)
                self.assertIn("(unnamed paths)", line[1])
        self.evidence(dirty_tree=True, dirty_paths=["ok", "\x1b[31mred\x1b[0m\nnext"])
        ((_, line),) = doctor_checks.dirty_evidence_lines(self.root)
        self.assertNotIn("\x1b", line)
        self.assertNotIn("\n", line)
        self.assertIn("(ok,  [31mred [0m next)", line)

    def test_doctor_reads_no_link_and_no_file_past_its_limit(self):
        self.evidence(dirty_tree=True, dirty_paths=["x"])
        evidence = self.root / ".aidd" / "evidence" / "evidence.json"
        elsewhere = self.root.parent / "elsewhere.json"
        elsewhere.write_text(evidence.read_text(encoding="utf-8"), encoding="utf-8")
        evidence.unlink()
        evidence.symlink_to(elsewhere)
        self.assertEqual(doctor_checks.dirty_evidence_lines(self.root), [])
        evidence.unlink()
        self.evidence(dirty_tree=True, dirty_paths=["x"], padding="x" * doctor_checks.EVIDENCE_MAX_BYTES)
        self.assertEqual(doctor_checks.dirty_evidence_lines(self.root), [])

    def test_doctor_is_quiet_for_a_clean_run_another_branch_or_no_evidence(self):
        self.assertEqual(doctor_checks.dirty_evidence_lines(self.root), [])
        self.evidence()
        self.assertEqual(doctor_checks.dirty_evidence_lines(self.root), [])
        git(self.root, "checkout", "-q", "--orphan", "other")
        git(self.root, "commit", "-q", "--allow-empty", "-m", "elsewhere")
        other = git(self.root, "rev-parse", "HEAD")
        git(self.root, "checkout", "-q", "feat")
        self.head = other
        self.evidence(dirty_tree=True, dirty_paths=["x"])
        self.assertEqual(doctor_checks.dirty_evidence_lines(self.root), [])
        self.head = "--output=/tmp/x"
        self.evidence(dirty_tree=True)
        self.assertEqual(doctor_checks.dirty_evidence_lines(self.root), [])


if __name__ == "__main__":
    unittest.main()
