"""How aidd reads a planned path a person or an agent types: one function, `arguments.planned_readings`, for every caller
(`aidd risk --paths`, `aidd status <path>`, `aidd new spec --paths`, and the MCP `risk` and `status` tools).

In a subfolder a relative path reads two ways: from the folder it was typed in, as a shell reads it, and from the
repository's top, as `git diff --name-only` prints it. aidd routes on both, so the stricter wins, and says so when they
differ. A folder keeps its trailing slash, so it stands for the files in it, also when typed without one. A path is read
as text, as git reads it, and also where a link inside the repository leads, so the stricter wins. A path outside the
repository, or an empty one, is an error with the next step, never `allow`."""

import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from helpers import git, make_repo, run_cli

from aidd.cli import arguments, mcp_server
from aidd.kernel import repo_paths

CONFIG_FILE = ".aidd/config.yaml"


class PlannedPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = make_repo(Path(cls.tmp.name) / "shop", branch=None)
        for rel in ("src/billing/charge.py", "src/web/app.js", "payments-svc/charge.py", ".github/workflows/ci.yml"):
            (cls.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (cls.root / rel).write_text("x\n", encoding="utf-8")
        (cls.root / "services").mkdir()
        os.symlink("../payments-svc", cls.root / "services" / "payments")
        os.symlink("loop-b", cls.root / "src" / "web" / "loop-a")
        os.symlink("loop-a", cls.root / "src" / "web" / "loop-b")
        os.symlink("../billing", cls.root / "src" / "web" / "billlink")
        git(cls.root, "add", "-A")
        git(cls.root, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "the shop")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def risk(self, folder: str, *paths: str) -> tuple[int, dict | str]:
        with contextlib.chdir(self.root / folder):
            code, out = run_cli("risk", "--json", "--paths", *paths)
        try:
            return code, json.loads(out)
        except json.JSONDecodeError:
            return code, out

    def level(self, folder: str, *paths: str) -> tuple[str, str]:
        code, answer = self.risk(folder, *paths)
        self.assertEqual(code, 0, answer)
        assert isinstance(answer, dict)
        return answer["route"], answer["edit"]["level"]

    def test_a_path_from_a_subfolder_routes_on_the_stricter_reading(self):
        # `git diff --name-only` prints paths from the top, so a subfolder never makes a top-level path read safer.
        rows = [
            ("src/web", CONFIG_FILE, ("normal", "ask")),  # the top's config, typed as git prints it
            ("src/web", ".github/workflows/ci.yml", ("normal", "report")),
            ("src/billing", "charge.py", ("major", "ask")),  # a billing file, typed where it lives
        ]
        for folder, path, expected in rows:
            with self.subTest(folder=folder, path=path):
                self.assertEqual(self.level(folder, path), expected)

    def test_two_readings_that_route_differently_say_so(self):
        with contextlib.chdir(self.root / "src" / "web"):
            code, out = run_cli("risk", "--paths", CONFIG_FILE)
        self.assertEqual(code, 0, out)
        self.assertIn(f"src/web/{CONFIG_FILE}", out)
        self.assertIn("reads two ways", out)
        # The next step names the paths as typed, so `aidd new spec` run from the same folder reads them the same way.
        self.assertIn(f"--paths {CONFIG_FILE}`", out)

    def test_the_next_step_names_the_paths_from_the_top(self):
        # Typed in src/billing, `charge.py` names src/billing/charge.py; run from the top, the step must mean the same file.
        with contextlib.chdir(self.root / "src" / "billing"):
            code, out = run_cli("risk", "--paths", "charge.py")
        self.assertEqual(code, 0, out)
        self.assertIn("--paths src/billing/charge.py`", out)
        self.assertNotIn("--paths charge.py`", out)
        self.assertEqual(self.level("", "src/billing/charge.py"), ("major", "ask"), "the printed path routes as the answer did")

    def test_a_folder_typed_without_a_slash_or_with_dots_is_a_folder(self):
        for folder, path, slashed in (
            ("", "src", "src/"),
            ("", ".github", ".github/"),
            ("", "src/billing/..", "src/"),
            ("src", "..", "./"),
            ("src/web", "../billing/..", "src/"),
        ):
            with self.subTest(folder=folder, path=path):
                self.assertEqual(self.level(folder, path), self.level("", slashed))
                self.assertNotEqual(self.level(folder, path)[0], "minor", "the folder holds files an area routes")

    def test_a_path_through_a_linked_parent_folder_is_inside(self):
        # macOS keeps /tmp as a link to /private/tmp: the top is found by its real path, the path is typed through the link.
        with tempfile.TemporaryDirectory() as d:
            real = Path(d).resolve() / "real"
            real.mkdir()
            os.symlink(real, Path(d).resolve() / "alias")
            root = make_repo(real / "shop", branch=None)
            (root / "src" / "billing").mkdir(parents=True)
            (root / "src" / "billing" / "charge.py").write_text("x\n", encoding="utf-8")
            with contextlib.chdir(root):
                code, out = run_cli("risk", "--json", "--paths", f"{d}/alias/shop/src/billing/charge.py")
            self.assertEqual(code, 0, out)
            self.assertEqual(json.loads(out)["route"], "major")
            with contextlib.chdir(root):
                code, out = run_cli("risk", "--json", "--paths", f"{d}/alias/elsewhere/x.py")
            self.assertEqual(code, 2, "a path through the link that is not in the repository stays outside")

    def test_a_link_inside_the_repository_also_reads_where_it_points(self):
        # src/web/billlink is a link to src/billing: an edit through it changes the billing file.
        for folder, path in (("", "src/web/billlink/charge.py"), ("src/web", "billlink/charge.py"), ("", "src/web/billlink/")):
            with self.subTest(folder=folder, path=path):
                self.assertEqual(self.level(folder, path)[0], "major", "the file it points to is in the billing area")

    def test_an_empty_path_is_refused_with_the_next_step(self):
        for paths in ([""], ["src/billing/charge.py", ""]):
            with self.subTest(paths=paths):
                code, out = self.risk("", *paths)
                self.assertEqual(code, 2, out)
                self.assertIn("empty", str(out))
                self.assertIn("src/billing/charge.py", str(out), "the next step gives a path to type")
        failed, text = mcp_server.call("risk", {"paths": [""]}, str(self.root))
        self.assertTrue(failed, text)
        self.assertIn("empty", text)

    def test_new_spec_scopes_the_folder_it_was_typed_in(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d) / "shop", branch=None)
            (root / "web").mkdir()
            (root / "package.json").write_text("{}\n", encoding="utf-8")
            with contextlib.chdir(root / "web"):
                code, out = run_cli("new", "spec", "Lint", "--paths", "package.json")
            self.assertEqual(code, 0, out)
            spec = next((root / "specs").glob("SPEC-*.md")).read_text(encoding="utf-8")
            self.assertIn("web/package.json", spec, "the file typed in web/, not the top's package.json")
            self.assertIn("scope takes web/package.json", out)
            self.assertIn("package.json from the repository's top", out)

    def test_a_folder_keeps_its_trailing_slash(self):
        for folder, path in (("", "src/"), ("", "./"), ("src", "./"), ("src", "billing/")):
            with self.subTest(folder=folder, path=path):
                self.assertEqual(self.level(folder, path)[0], "major", "a folder that holds a billing file")

    def test_a_link_inside_the_repository_reads_as_typed(self):
        self.assertEqual(self.level("", "services/payments/charge.py")[0], "major", "the payments area, as git reads the path")

    def test_a_link_loop_reads_as_text(self):
        # Python 3.11 and 3.12 raise "Symlink loop" from resolve(); a path read as text never follows the link.
        code, answer = self.risk("src/web", "loop-a/x.js")
        self.assertEqual(code, 0, answer)
        with contextlib.chdir(self.root / "src" / "web"):
            code, out = run_cli("status", "loop-a", "--json")
        self.assertEqual(code, 0, out)

    def test_a_new_file_named_like_an_id_reads_both_ways(self):
        self.assertEqual(self.level("src/billing", "refund-2")[0], "major", "src/billing/refund-2 is in the payments area")

    def test_a_path_outside_the_repository_is_an_error_with_the_next_step(self):
        for path in ("/etc/passwd", "../../../other/x.py", "../../../shop-other/.aidd/config.yaml"):
            with self.subTest(path=path):
                code, out = self.risk("src", path)
                self.assertEqual(code, 2, out)
                self.assertIn("outside", str(out))
                self.assertIn("repository", str(out))

    def test_the_mcp_tool_reads_paths_from_the_top_and_keeps_a_folder(self):
        for path, route in (("src/", "major"), ("./", "major"), ("services/payments/charge.py", "major")):
            with self.subTest(path=path):
                failed, text = mcp_server.call("risk", {"paths": [path]}, str(self.root))
                self.assertFalse(failed, text)
                self.assertEqual(json.loads(text)["route"], route)
        failed, text = mcp_server.call("risk", {"paths": ["../x"]}, str(self.root))
        self.assertTrue(failed)

    def test_status_of_a_path_reads_it_the_same_way(self):
        with contextlib.chdir(self.root / "src" / "web"):
            code, out = run_cli("status", CONFIG_FILE, "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["risk"]["route"], "normal", "the stricter reading routes it")

    def test_new_spec_routes_and_scopes_as_risk_does(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d) / "shop", branch=None)
            (root / "src" / "billing").mkdir(parents=True)
            (root / "src" / "billing" / "charge.py").write_text("x\n", encoding="utf-8")
            with contextlib.chdir(root / "src" / "billing"):
                code, out = run_cli("new", "spec", "Refunds", "--paths", "charge.py")
            self.assertEqual(code, 0, out)
            self.assertIn("route: the least route for these paths is major", out)
            spec = next((root / "specs").glob("SPEC-*.md")).read_text(encoding="utf-8")
            self.assertIn("src/billing/charge.py", spec)


class AFolderTypedWithoutASlashReadsBothWays(unittest.TestCase):
    """A pattern that names the folder itself, such as `**/secrets.*` for `conf/secrets.d`, matches the text without a slash
    only. A pattern for the files in it matches the text with one. Both readings route, so the stricter wins."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_repo(Path(tmp.name) / "shop", branch=None)
        for rel in (
            "conf/secrets.d/x.conf",
            "src/session.store/y.py",
            "src/plain.py",
            "src/billing/charge.py",
            ".github/sub/a.txt",
            ".github/workflows/ci.yml",
        ):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text("x\n", encoding="utf-8")
        os.symlink("billing", self.root / "src" / "billlink")
        os.symlink("../.github/sub", self.root / "src" / "cilink")
        self.top = str(self.root)

    def every(self, *typed: str, folder: str = "") -> list[str]:
        return arguments.planned_readings(list(typed), self.root, self.root / folder).every

    def test_a_folder_typed_without_a_slash_is_read_with_and_without_it(self):
        self.assertEqual(repo_paths.readings("conf/secrets.d", top=self.top, here=""), ["conf/secrets.d/"], "the text reading keeps its one slash")
        self.assertEqual(self.every("conf/secrets.d"), ["conf/secrets.d/", "conf/secrets.d"])
        self.assertEqual(self.every("conf/secrets.d/"), ["conf/secrets.d/"])
        self.assertEqual(self.every("src/plain.py"), ["src/plain.py"])
        self.assertEqual(self.every("src/billing/")[0], "src/billing/")
        for path, area in (("conf/secrets.d", "secrets"), ("src/session.store", "auth")):
            with self.subTest(path=path), contextlib.chdir(self.root):
                code, out = run_cli("risk", "--json", "--paths", path)
                self.assertEqual(code, 0, out)
                self.assertIn(area, [a["area"] for a in json.loads(out)["areas"]])

    def test_a_link_to_a_folder_typed_without_a_slash_also_reads_the_folders_files(self):
        self.assertIn("src/billing/", self.every("src/billlink"))
        self.assertIn("src/billing", self.every("src/billlink"))

    def test_a_dot_dot_after_a_link_goes_up_from_where_the_link_leads(self):
        # The text folds `cilink/..` to `src`; the system goes up from `.github/sub`, which is `.github`.
        for folder, typed in (("", "src/cilink/../workflows/ci.yml"), ("src", "cilink/../workflows/ci.yml")):
            with self.subTest(folder=folder):
                self.assertIn(".github/workflows/ci.yml", self.every(typed, folder=folder))
        self.assertEqual(self.every("src/plain.py"), ["src/plain.py"], "a path with no link has no other reading")


if __name__ == "__main__":
    unittest.main()
