"""A test command may name the folder it runs in (`runs_in`), so a monorepo gives each package its own command.

Invariants:

- A command runs in its `runs_in` folder, and in the repository's top without one. `when_changed` and `report` keep their meaning
  relative to the top, never the folder.
- A folder outside the repository, or reached through a link, runs nothing and writes no evidence: the config fails to load, and
  a Spec's command, which the config's load never sees, is stopped by the runner before any command runs. A folder that is not
  there is a command that did not start, which proves nothing.
- The head cannot move a base command to another folder to make it pass: a changed command is a changed command, so the base's copy
  runs too, in the base's folder (tests/test_base_view.py holds the table over the data).
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

import helpers  # noqa: F401  # the hermetic environment
from spec_repo_fixtures import PASS, RepoCase, config_text, spec_text

from aidd import config, testing
from aidd.testing import runner

WHERE = "import os; print('cwd=' + os.path.realpath(os.getcwd()))"
MONOREPO = (
    ("api", WHERE, ["packages/api/**"], "packages/api"),
    ("web", WHERE, ["packages/web/**"], "packages/web"),
    ("inner", WHERE, ["src/**"], "packages/api"),
)


class MonorepoTests(RepoCase):
    def monorepo(self, tests=MONOREPO, extra: str = "") -> None:
        for package in ("api", "web"):
            self.put(self.root, f"packages/{package}/src/main.py", "x = 1\n")
        self.put(self.root, ".aidd/config.yaml", config_text(*tests, extra=extra))
        self.commit(self.root, "a monorepo of two packages")
        self.branch()

    def test_each_package_command_runs_in_its_own_folder_and_is_selected_by_a_path_from_the_top(self):
        cases = [
            # (the paths the change touches, the commands that run)
            (["packages/api/src/a.py"], {"api"}),
            (["packages/web/src/b.py"], {"web"}),
            (["packages/api/src/a.py", "packages/web/src/b.py"], {"api", "web"}),
            (["README.md"], set()),
            (["src/top.py"], {"inner"}),  # `src/**` is a path from the top: it matches `src/top.py`, never `packages/api/src/a.py`
        ]
        for paths, expected in cases:
            with self.subTest(paths=paths):
                self.fresh()
                self.monorepo()
                for rel in paths:
                    self.put(self.root, rel, "y = 2\n")
                self.commit(self.root, "the change")
                evidence, _ = self.run_aidd(red=False)
                ran = {r["name"]: r for r in evidence["results"]}
                self.assertEqual(set(ran), expected)
                for name, _code, _when, folder in MONOREPO:
                    if name in ran:
                        log = (self.root / ".aidd" / "evidence" / ran[name]["log"]).read_text(encoding="utf-8")
                        self.assertIn(f"cwd={os.path.realpath(self.root / folder)}", log, f"{name} ran in the wrong folder")
                        self.assertEqual(ran[name]["runs_in"], folder)

    def test_a_command_with_no_folder_runs_at_the_top(self):
        self.monorepo(tests=(("top", WHERE, []),))
        self.put(self.root, "packages/api/src/a.py", "y = 2\n")
        self.commit(self.root, "the change")
        result = self.run_aidd(red=False)[0]["results"][0]
        self.assertIn(f"cwd={os.path.realpath(self.root)}", (self.root / ".aidd" / "evidence" / result["log"]).read_text(encoding="utf-8"))
        self.assertNotIn("runs_in", result)

    def test_a_folder_that_is_not_there_is_a_command_that_did_not_start(self):
        self.monorepo(tests=(("gone", PASS, [], "packages/missing"),))
        self.put(self.root, "app/x.py", "y = 2\n")
        self.commit(self.root, "the change")
        evidence, _ = self.run_aidd(red=False)
        self.assertEqual([(r["status"], r["exit"]) for r in evidence["results"]], [("not_started", None)])
        self.assertEqual(testing.exit_code(evidence), 1)

    def test_a_package_command_s_red_run_on_the_base_happens_in_the_same_folder(self):
        """The new file exists only on the head, in the package: the command fails on the base and passes on the head, each in the folder."""
        self.put(self.root, "packages/api/src/main.py", "x = 1\n")
        self.commit(self.root, "a package")
        self.branch()
        code = "import os; raise SystemExit(0 if os.path.exists('src/new.py') else 1)"
        self.put(self.root, "specs/SPEC-1.md", spec_text("SPEC-1", status="in_progress", code=code, new_behavior=True, runs_in="packages/api"))
        self.put(self.root, "packages/api/src/new.py", "y = 2\n")
        self.commit(self.root, "the feature and its Spec")
        evidence, _ = self.run_aidd()
        spec = {r["red_green"]: r for r in evidence["results"] if r["name"] == "check"}
        self.assertEqual((spec["green"]["exit"], spec["green"]["runs_in"]), (0, "packages/api"))
        self.assertEqual((spec["red"]["exit"], spec["red"]["runs_in"]), (1, "packages/api"))
        self.assertTrue(testing.red_ok(spec["red"]))


class BaseCommandsKeepTheirFolder(RepoCase):
    """The head cannot move a base command to another folder to make it pass."""

    def test_a_head_that_moves_the_folder_of_a_base_command_runs_the_base_s_copy_in_the_base_s_folder(self):
        failing = "import os; raise SystemExit(1 if os.path.exists('broken.txt') else 0)"
        cases = [
            # (the folder the head gives the command, what runs, exit)
            ("packages/web", {"unit", "base.unit"}, 1),  # moved to a folder where the command passes: the base's copy still fails in packages/api
            ("packages/api", {"unit"}, 1),  # unchanged: it fails where it always did
        ]
        for folder, ran, code in cases:
            with self.subTest(head=folder):
                self.fresh()
                for package in ("api", "web"):
                    self.put(self.root, f"packages/{package}/src/main.py", "x = 1\n")
                self.put(self.root, "packages/api/broken.txt", "broken\n")
                self.put(self.root, ".aidd/config.yaml", config_text(("unit", failing, [], "packages/api")))
                self.commit(self.root, "base")
                self.branch()
                self.put(self.root, ".aidd/config.yaml", config_text(("unit", failing, [], folder)))
                self.put(self.root, "app/x.py", "y = 2\n")
                self.commit(self.root, "the head")
                evidence, notes = self.run_aidd(red=False)
                self.assertEqual({r["name"] for r in evidence["results"]}, ran)
                self.assertEqual(testing.exit_code(evidence), code)
                copy = [r for r in evidence["results"] if r["name"] == "base.unit"]
                self.assertEqual([r["runs_in"] for r in copy], ["packages/api"] * len(copy))
                self.assertEqual(any("changes or removes `tests`" in n for n in notes), folder != "packages/api")

    def test_a_head_that_moves_the_folder_of_an_approved_specs_command_runs_the_base_s_copy_too(self):
        failing = "import os; raise SystemExit(1 if os.path.exists('broken.txt') else 0)"
        for folder, ran, code in (("packages/web", {"check", "base.check"}, 1), ("packages/api", set(), 0)):  # an untouched Spec is not run at all
            with self.subTest(head=folder):
                self.fresh()
                for package in ("api", "web"):
                    self.put(self.root, f"packages/{package}/src/main.py", "x = 1\n")
                self.put(self.root, "packages/api/broken.txt", "broken\n")
                self.put(self.root, "specs/SPEC-1.md", spec_text("SPEC-1", status="approved", code=failing, new_behavior=True, runs_in="packages/api"))
                self.commit(self.root, "the approved Spec")
                self.branch()
                self.put(self.root, "specs/SPEC-1.md", spec_text("SPEC-1", status="approved", code=failing, new_behavior=True, runs_in=folder))
                self.put(self.root, "app/x.py", "y = 2\n")
                self.commit(self.root, "the head")
                evidence, notes = self.run_aidd(red=False)
                self.assertEqual({r["name"] for r in evidence["results"]} - {"unit"}, ran)
                self.assertEqual(testing.exit_code(evidence), code, "the base's command still fails in its own folder")
                self.assertEqual([r["runs_in"] for r in evidence["results"] if r["name"] == "base.check"], ["packages/api"] * (folder != "packages/api"))


@unittest.skipIf(os.name == "nt", "a symlink needs no privilege on POSIX only")
class AFolderOutsideOrThroughALinkRunsNothing(RepoCase):
    ROWS = {
        "a link as the folder": "packages/link",
        "a link in the middle": "packages/link/api",
        "a link to a folder inside the repository": "packages/inside",
        "a link at the end of a longer path": "packages/api/down",
    }

    def tree(self) -> None:
        self.put(self.root, "elsewhere/api/x.py", "x = 1\n")
        self.put(self.root, "packages/api/x.py", "x = 1\n")
        os.symlink("../elsewhere", self.root / "packages/link")
        os.symlink("api", self.root / "packages/inside")
        os.symlink("../../elsewhere", self.root / "packages/api/down")

    def test_a_spec_command_through_a_link_runs_nothing_and_writes_no_evidence(self):
        marker = "open('marker.txt', 'w').write('ran')"
        for name, folder in self.ROWS.items():
            with self.subTest(name):
                self.fresh()
                self.tree()
                self.commit(self.root, "base")
                self.branch()
                self.put(self.root, "specs/SPEC-1.md", spec_text("SPEC-1", status="in_progress", code=marker, runs_in=folder))
                self.commit(self.root, "the Spec")
                with self.assertRaises(RuntimeError) as cm:
                    self.run_aidd(red=False)
                self.assertIn("runs_in", str(cm.exception))
                self.assertIn("then run `aidd test` again", str(cm.exception))
                self.assertEqual(list(self.root.rglob("marker.txt")), [], "no command ran")
                self.assertFalse((self.root / ".aidd" / "evidence" / "evidence.json").exists())

    def test_a_config_command_through_a_link_fails_the_config_load_with_the_next_step(self):
        for name, folder in self.ROWS.items():
            with self.subTest(name):
                self.fresh()
                self.tree()
                self.put(self.root, ".aidd/config.yaml", config_text(("unit", PASS, [], folder)))
                with self.assertRaises(config.ConfigError) as cm:
                    config.load_file(config.CONFIG_PATH, str(self.root))
                self.assertIn("runs_in", str(cm.exception))
                self.assertIn("then run aidd again", str(cm.exception))


class CommandFolderTable(unittest.TestCase):
    def test_the_folder_is_the_top_or_a_folder_inside_it_through_no_link(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            top = Path(d, "repo")
            (top / "packages/api").mkdir(parents=True)
            (top / "packages/file").write_text("x", encoding="utf-8")
            if os.name != "nt":
                os.symlink("api", top / "packages/link")
            rows = [
                ({}, str(top)),
                ({"runs_in": ""}, str(top)),
                ({"runs_in": "packages/api"}, str(top / "packages/api")),
                ({"runs_in": "packages/api/"}, str(top / "packages/api/")),
                ({"runs_in": "packages/missing"}, str(top / "packages/missing")),  # the command then does not start; nothing links out
            ]
            for command, expected in rows:
                with self.subTest(command=command):
                    self.assertEqual(runner.command_folder(str(top), {"name": "x", **command}), expected)
            refused = ["../outside", "packages/../../outside", "/etc"]
            if os.name != "nt":
                refused += ["packages/link", "packages/link/x"]
            for folder in refused:
                with self.subTest(refused=folder), self.assertRaises(RuntimeError) as cm:
                    runner.command_folder(str(top), {"name": "x", "runs_in": folder})
                self.assertIn("then run `aidd test` again", str(cm.exception))

    def test_the_schema_refuses_a_folder_that_climbs_out_before_anything_loads(self):
        for folder in ("../outside", "a/../../b", "/etc", "./packages", "packages\\api", "packages/*"):
            with self.subTest(folder=folder), self.assertRaises(config.ConfigError) as cm:
                config.load_text(config_text(("unit", PASS, [], folder)))
            self.assertIn("runs_in", str(cm.exception))
        for folder in ("packages/api", "packages/api/", "pkg", "a/b/c"):
            with self.subTest(folder=folder):
                self.assertEqual(config.load_text(config_text(("unit", PASS, [], folder))).tests[0]["runs_in"], folder)


if __name__ == "__main__":
    unittest.main()
