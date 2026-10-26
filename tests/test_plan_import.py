"""`aidd import speckit|openspec|kiro|bmad`: a short aidd Spec from another planning tool's files.

The fixtures under tests/fixtures/import/ follow each tool's current templates (checked 2026-09-28; the formats are
listed in src/aidd/setup/plan_import.py). The Spec quotes the source's words in Intent and links every file it read, gives
each acceptance scenario or EARS requirement an id, takes each Task's scope from the paths the source names, computes
the route from them, and leaves tests.files and the test command TODO: it never invents a test.
"""

import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, make_repo, run_cli

from aidd.cli import parser as cli_parser
from aidd.setup import plan_import
from aidd.workitems import spec_file

FIXTURES = ROOT / "tests" / "fixtures" / "import"
TODO_ERROR = "test commands, tests.files, or a Task's scope still hold TODO placeholders"


@unittest.skipUnless(shutil.which("git"), "git is required")
class ImportCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = make_repo(Path(self.tmp.name) / "repo", "team")
        here = os.getcwd()
        self.addCleanup(os.chdir, here)
        os.chdir(self.root)

    def run_import(self, tool: str, rel: str, *extra: str, copy: bool = True) -> tuple[Path, dict, str, str]:
        if copy:
            shutil.copytree(FIXTURES / tool, self.root, dirs_exist_ok=True)
        code, out = run_cli("import", tool, rel, *extra)
        self.assertEqual(code, 0, out)
        path = self.root / out.splitlines()[0]
        data, body, errs = spec_file.load_object(path.read_text(encoding="utf-8"), str(path))
        self.assertEqual(errs, [], errs)
        return path, data, body, out

    def acceptance(self, body: str) -> list[str]:
        return re.findall(r"(?m)^- (A\d+): ", body)

    def assert_links_resolve(self, path: Path, body: str, count: int) -> None:
        intent = body.split("## Intent", 1)[1].split("\n## ", 1)[0]
        (source,) = [x for x in intent.splitlines() if x.startswith("Source: ")]
        links = re.findall(r"\]\(([^)]+)\)", source)
        self.assertEqual(len(links), count, source)
        for link in links:
            self.assertTrue((path.parent / link).is_file(), link)

    def assert_validates_but_for_the_tests(self, path: Path) -> None:
        """Only the TODOs aidd import leaves on purpose fail validation; once a person names the tests, it validates."""
        rel = path.relative_to(self.root).as_posix()
        code, out = run_cli("validate", rel)
        self.assertEqual(code, 1)
        errors = [x for x in out.splitlines() if x.startswith("error")]
        self.assertEqual(errors, [f"error: {rel}: {TODO_ERROR}"], out)
        text = path.read_text(encoding="utf-8")
        text = re.sub(r'(?m)^( +)files: \["tests/TODO"\].*$', r"\1files: [tests/test_feature.py]", text, count=1)
        text = text.replace('command: ["TODO"]', "command: [python3, tests/test_feature.py]", 1)
        path.write_text(text, encoding="utf-8")
        code, out = run_cli("validate", rel)
        self.assertEqual([x for x in out.splitlines() if x.startswith("error")], [], out)

    def scopes(self, data: dict) -> list[list[str]]:
        return [t["scope"] for t in data["tasks"]]


class SpecKitTests(ImportCase):
    def test_a_feature_folder_becomes_a_short_spec(self):
        path, data, body, out = self.run_import("speckit", "specs/001-photo-albums")
        self.assertEqual(path, self.root / "specs" / "SPEC-1.md")
        self.assertEqual((data["title"], data["type"], data["route"]), ("Photo albums", "feat", "normal"))
        self.assertIn("> Let people group their photos into albums", body)  # the originator's words, quoted
        self.assertEqual(self.acceptance(body), ["A1", "A2", "A3"])
        self.assertIn('- A3: Given albums "A" then "B", When the user drags', body)
        self.assertIn("(User Story 2)", body)
        # One Task per phase that names a path; the phases share files, so the later one depends on the earlier.
        self.assertEqual(self.scopes(data), [["src/models/", "src/services/"]] * 2)  # each file's folder (workitems.folder_scope)
        self.assertEqual(data["tasks"][1]["depends_on"], [data["tasks"][0]["id"]])
        self.assertEqual(data["tests"]["files"], ["tests/TODO"])  # never invented
        self.assertIn("tests/contract/test_albums.py", path.read_text(encoding="utf-8"))  # named in a comment only
        self.assertIn("[plan.md](001-photo-albums/plan.md): Albums are a new table", body)
        self.assert_links_resolve(path, body, 3)
        self.assertIn("route: normal", out)
        self.assert_validates_but_for_the_tests(path)

    def test_without_scenarios_the_functional_requirements_are_the_acceptance(self):
        shutil.copytree(FIXTURES / "speckit", self.root, dirs_exist_ok=True)
        spec = self.root / "specs" / "001-photo-albums" / "spec.md"
        spec.write_text(re.sub(r"(?m)^\d\. \*\*Given\*\*.*$", "", spec.read_text(encoding="utf-8")), encoding="utf-8")
        _, _, body, _ = self.run_import("speckit", "specs/001-photo-albums/spec.md", "--id", "ALB-1", copy=False)
        self.assertIn("- A1: System MUST let users create an album from selected photos (FR-001)", body)
        self.assertTrue((self.root / "specs" / "ALB-1.md").is_file())


class TaskOrderTests(unittest.TestCase):
    def test_two_tasks_on_different_files_of_one_folder_still_run_side_by_side(self):
        from aidd.setup import plan_import
        from aidd.kernel import documents

        groups = [plan_import.Group("a", ["src/x/a.py"]), plan_import.Group("b", ["src/x/b.py"])]
        text = plan_import._tasks_yaml("SPEC-1", groups, [["src/x/"], ["src/x/"]])
        tasks = documents.parse_yaml(text, "tasks")["tasks"]
        self.assertEqual([t["scope"] for t in tasks], [["src/x/"], ["src/x/"]])
        self.assertNotIn("depends_on", tasks[1])  # by the files they name, not the folder their scope widens to


class OpenSpecTests(ImportCase):
    def test_a_change_folder_becomes_a_short_spec(self):
        path, data, body, _ = self.run_import("openspec", "openspec/changes/add-dark-mode")
        self.assertEqual(data["title"], "Add dark mode")
        self.assertIn("> People reading at night find the white interface glaring", body)
        self.assertEqual(self.acceptance(body), ["A1", "A2"])  # ADDED scenarios; the REMOVED requirement is not one
        self.assertIn("- A1: Theme selection / Choosing dark: when the user selects the dark theme, then every page renders", body)
        self.assertEqual(self.scopes(data), [["web/src/theme/"], ["web/src/settings/"]])
        self.assertNotIn("depends_on", data["tasks"][1])
        self.assertIn("design.md", body.split("## Design", 1)[1])
        self.assert_links_resolve(path, body, 4)
        self.assert_validates_but_for_the_tests(path)


class KiroTests(ImportCase):
    def test_ears_requirements_become_acceptance_items(self):
        path, data, body, out = self.run_import("kiro", ".kiro/specs/user-auth", "--out", "work/specs")
        self.assertEqual(path, self.root / "work" / "specs" / "SPEC-1.md")
        self.assertIn("> Customers cannot sign in with their email today", body)
        self.assertEqual(self.acceptance(body), ["A1", "A2", "A3"])
        self.assertIn("- A1: WHEN a customer submits a registered email and the right password THEN the system SHALL start a session (Requirement 1)", body)
        # The docs' two-line form is one requirement.
        self.assertIn("- A3: WHEN a customer fails to sign in five times within ten minutes THE SYSTEM SHALL lock the account", body)
        self.assertEqual(self.scopes(data), [["src/auth/session.py", "src/api/"], ["src/auth/lockout.py"]])  # a risky file stays exact
        # An auth path: the route is computed from the paths, as `aidd new spec --paths` does.
        self.assertEqual((data["route"], data["risk"]["dimensions"]), ("major", ["security"]))
        self.assertIn("rule baseline:auth", out)
        self.assert_links_resolve(path, body, 3)
        self.assert_validates_but_for_the_tests(path)

    def test_a_bugfix_spec_is_a_fix_with_the_expected_and_unchanged_behavior(self):
        path, data, body, out = self.run_import("kiro", ".kiro/specs/login-timeout-bug")
        self.assertEqual(data["type"], "fix")
        self.assertIn("> WHEN a session is idle for exactly 30 minutes THEN the system signs the user out", body)
        self.assertEqual(self.acceptance(body), ["A1", "A2"])
        self.assertIn("SHALL CONTINUE TO sign the user out", body)
        # No path named: the template's TODO scope stays, and validate flags it.
        self.assertEqual(self.scopes(data), [["src/TODO/"]])
        self.assertIn("could not be computed", out)
        self.assertIn("the Task's scope", out)


class BmadTests(ImportCase):
    def test_one_story_becomes_one_spec(self):
        rel = "_bmad-output/implementation-artifacts/1-2-password-reset.md"
        path, data, body, _ = self.run_import("bmad", rel)
        self.assertEqual(data["title"], "Password reset by email")
        intent = body.split("## Intent", 1)[1].split("\n## ", 1)[0]
        self.assertIn("> As a customer who forgot my password,", intent)
        self.assertNotIn("Status: ready-for-dev", intent)
        self.assertEqual(self.acceptance(body), ["A1", "A2"])
        self.assertEqual(self.scopes(data), [["app/auth/reset_tokens.py"], ["app/views/"]])
        self.assertEqual(data["tests"]["files"], ["tests/TODO"])
        self.assert_links_resolve(path, body, 1)

    def test_a_folder_is_refused(self):
        shutil.copytree(FIXTURES / "bmad", self.root, dirs_exist_ok=True)
        code, out = run_cli("import", "bmad", "_bmad-output/implementation-artifacts")
        self.assertEqual(code, 2)
        self.assertIn("one story becomes one Spec", out)


class ImportRulesTests(ImportCase):
    def test_ids_count_up_and_an_existing_spec_is_never_overwritten(self):
        self.run_import("openspec", "openspec/changes/add-dark-mode")
        path, *_ = self.run_import("openspec", "openspec/changes/add-dark-mode")
        self.assertEqual(path.name, "SPEC-2.md")
        code, out = run_cli("import", "openspec", "openspec/changes/add-dark-mode", "--id", "SPEC-1")
        self.assertEqual(code, 2)
        self.assertIn("exists", out)

    def test_a_folder_without_the_tools_files_is_refused(self):
        for tool, want in (("speckit", "no spec.md"), ("openspec", "no proposal.md"), ("kiro", "no requirements.md or bugfix.md")):
            with self.subTest(tool=tool):
                code, out = run_cli("import", tool, ".")
                self.assertEqual(code, 2)
                self.assertIn(want, out)

    def test_paths_are_only_what_the_source_names(self):
        line = "Create `src/models/[entity].py` and src/app.py, see https://example.com/a/b.py, `README.md`, and/or ~/x/y.py, `/etc/passwd`"
        self.assertEqual(plan_import.paths_in(line), ["README.md", "src/app.py"])
        self.assertEqual(plan_import.paths_in("Node.js and e.g. v1.2 in src/"), ["src/"])
        for test_path in ("tests/test_a.py", "web/tests/theme.test.ts", "pkg/a_test.go", "src/__tests__/x.js", "app/spec/models/a_spec.rb"):
            self.assertTrue(plan_import.is_test_path(test_path), test_path)
        self.assertFalse(plan_import.is_test_path("src/services/albums.py"))

    def test_the_cli_documents_every_tool(self):
        parser = cli_parser.build_parser()
        out = parser._subparsers._group_actions[0].choices["import"].format_help()  # type: ignore[union-attr]
        for tool in plan_import.TOOLS:
            self.assertIn(tool, out)


if __name__ == "__main__":
    unittest.main()
