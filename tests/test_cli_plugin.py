"""The aidd-cli plugin: `aidd` on the PATH of Claude Code's Bash tool, from a copy of aidd's own source and data.

It is made of links. Claude Code copies a marketplace plugin into its cache and dereferences each link to elsewhere in
the marketplace, so the copy holds real files: `bin/aidd` is the aidd plugin's `scripts/aidd`, and beside it the source
and every data folder aidd reads, at the paths a source checkout has them (`kernel/resources.py`). A plugin with a
`bin/` folder is one claude.ai and Cowork refuse, which is why this is not the aidd plugin itself.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

from helpers import IN_GIT_CHECKOUT, ROOT

from aidd.kernel import resources

CLI = ROOT / "plugins" / "aidd-cli"
# The sdist leaves the folder links out (pyproject.toml), since hatchling would copy each target in again, and git on
# Windows checks links out as text. Everywhere else a checkout holds them.
LINKS_IN_THIS_TREE = unittest.skipUnless(
    IN_GIT_CHECKOUT and (sys.platform != "win32" or os.path.islink(CLI / "bin" / "aidd")), "this tree holds no links: the sdist, or git on Windows"
)


class CliPluginTest(unittest.TestCase):
    @LINKS_IN_THIS_TREE
    def test_every_part_links_into_the_marketplace(self):
        links = {"bin/aidd": "scripts/aidd", "src": "src", **{v: v for v in resources._LAYOUT.values()}}
        for part, target in links.items():
            with self.subTest(part=part):
                path = CLI / part
                self.assertTrue(path.is_symlink(), f"{part} must be a link, so the plugin holds no second copy")
                self.assertEqual(path.resolve(), (ROOT / target).resolve())
                self.assertFalse(Path(os.readlink(path)).is_absolute(), f"{part} must link relatively")

    @LINKS_IN_THIS_TREE
    def test_it_holds_only_its_links_and_manifest(self):
        files = sorted(p.relative_to(CLI).as_posix() for p in CLI.rglob("*") if p.is_symlink() or (p.is_file() and not any(q.is_symlink() for q in p.parents)))
        expected = sorted(["bin/aidd", "src", ".claude-plugin/plugin.json", *resources._LAYOUT.values()])
        self.assertEqual(files, expected)
        self.assertNotIn("bin", [p.name for p in ROOT.iterdir()], "the aidd plugin itself keeps no bin/, so claude.ai and Cowork install it")

    def test_the_sdist_leaves_out_exactly_the_folder_links(self):
        exclude = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["hatch"]["build"]["targets"]["sdist"]["exclude"]
        tops = {"src", *(v.split("/")[0] for v in resources._LAYOUT.values())}
        self.assertEqual(sorted(exclude), sorted(f"plugins/aidd-cli/{top}" for top in tops))
        # hatchling follows links and keeps the first path it reaches to each folder: without the pruning, a link it
        # entered first took the real src/ and schemas/ out of the sdist.
        sdist = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["hatch"]["build"]["targets"]["sdist"]
        self.assertIs(sdist["skip-excluded-dirs"], True)

    def test_the_marketplace_lists_it_with_no_dependency(self):
        market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        entry = next(p for p in market["plugins"] if p["name"] == "aidd-cli")
        self.assertEqual(entry["source"], "./plugins/aidd-cli")
        self.assertNotIn("dependencies", entry)
        self.assertEqual(json.loads((CLI / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["name"], "aidd-cli")

    @LINKS_IN_THIS_TREE
    @unittest.skipIf(sys.platform == "win32", "the launcher is sh")
    def test_a_copy_with_the_links_dereferenced_runs_aidd(self):
        """As Claude Code's cache holds it: real files, outside any repository."""
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "aidd-cli"
            shutil.copytree(CLI, copy, symlinks=False, ignore=shutil.ignore_patterns("__pycache__"))
            self.assertFalse(any(p.is_symlink() for p in copy.rglob("*")))
            work = Path(tmp) / "work"
            env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "CLAUDE_PROJECT_DIR"))}
            subprocess.run(["git", "init", "-q", str(work)], env=env, check=True, timeout=60)
            r = subprocess.run([str(copy / "bin" / "aidd"), "stack", "list"], cwd=work, env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("standards:", r.stdout)

    @LINKS_IN_THIS_TREE
    @unittest.skipIf(sys.platform == "win32", "the launcher is sh")
    def test_in_place_it_refuses_a_folder_inside_its_own_source(self):
        """A marketplace added from a local path loads the plugin in place, and Claude Code's Bash tool sets no
        CLAUDE_PROJECT_DIR: from a subfolder of that checkout, aidd would run the working tree's own code."""
        env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "CLAUDE_PROJECT_DIR"))}
        for folder in (ROOT, ROOT / "docs", ROOT / "src" / "aidd"):
            with self.subTest(folder=folder.name):
                r = subprocess.run([str(CLI / "bin" / "aidd"), "--version"], cwd=folder, env=env, capture_output=True, text=True, timeout=60)
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertIn("run aidd from your own install here", r.stderr)


if __name__ == "__main__":
    unittest.main()
