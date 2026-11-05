"""aidd finds its bundled data (schemas, the skill, the CI templates, the aidd-team plugin, the standards library and
stacks) when it runs installed, not only from this checkout.

`resources` locates the data from the package's own folder: `aidd/_data` in a wheel, the archive in the zipapp, and the
repository root in a checkout. A checkout falls back to the repository root, so a wrong package folder (`resources`
moved one level down, into a subpackage) still passes every other test here and breaks only the installed forms. Each
form runs in a child interpreter, isolated (-I), with this checkout nowhere on its path:

- a wheel-shaped tree, laid out from pyproject.toml's wheel sources map with no build backend (always);
- the zipapp, built by `aidd.pyz` (always);
- a real wheel, built with the hash-locked backend and installed into a fresh venv (where BUILD_WHEEL_TEST=1 and uv
  are set, as ci.yml's test job does).
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

from helpers import ROOT

from aidd import pyz
from aidd.kernel import resources

# A file each data folder must hold.
MARKERS = {
    "schemas": "profiles.json",
    "skill": "SKILL.md",
    "templates": "AGENTS.snippet.md",
    "team": ".claude-plugin/plugin.json",
    "standards": "python/import-linter.md",
    "stacks": "python-cli.yaml",
}

# Prints where the running aidd finds each data folder. With an argument, that path goes first on sys.path.
PROBE = """import json, sys
if len(sys.argv) > 1:
    sys.path.insert(0, sys.argv[1])
import aidd
from aidd.kernel import resources
print(json.dumps({
    "package": aidd.__file__,
    "repo_root": None if resources.repo_root() is None else str(resources.repo_root()),
    "profiles": sorted(resources.load_json("profiles.json")["profiles"]),
    "data": {name: str(resources.data_dir(name)) for name in resources._LAYOUT},
}))
"""


def isolated_env(tmp: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    return env | {"XDG_CACHE_HOME": str(tmp / "cache"), "HOME": str(tmp / "home")}


class BundledDataTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()

    def probe(self, python: str, *path: str, cwd: Path) -> dict:
        run = subprocess.run(
            [python, "-I", "-c", PROBE, *path], cwd=cwd, env=isolated_env(self.tmp), capture_output=True, text=True, encoding="utf-8", timeout=120
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout)

    def assert_bundled(self, found: dict, inside: Path) -> None:
        """Every data folder resolves inside `inside` (the install), holds its marker, and none comes from the checkout."""
        self.assertIsNone(found["repo_root"])
        self.assertFalse(Path(found["package"]).resolve().is_relative_to(ROOT), found["package"])
        self.assertEqual(set(found["data"]), set(resources._LAYOUT))
        self.assertIn("solo", found["profiles"])
        for name, folder in found["data"].items():
            with self.subTest(name):
                folder = Path(folder).resolve()
                self.assertTrue(folder.is_relative_to(inside), f"{name}: {folder} is outside {inside}")
                self.assertFalse(folder.is_relative_to(ROOT), f"{name}: {folder} is the checkout's")
                self.assertTrue((folder / MARKERS[name]).is_file(), f"{name}: no {MARKERS[name]} in {folder}")

    def test_a_wheel_shaped_install_reads_its_own_data(self):
        sources = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["hatch"]["build"]["targets"]["wheel"]["sources"]
        site = self.tmp / "site-packages"
        for source, target in sources.items():
            shutil.copytree(ROOT / source, site / target, ignore=shutil.ignore_patterns("__pycache__", "results", "node_modules"))
        self.assert_bundled(self.probe(sys.executable, str(site), cwd=self.tmp), site / "aidd")

    def test_the_zipapp_reads_its_own_data(self):
        archive = pyz.build(self.tmp / "out" / "aidd.pyz", ROOT)
        self.assert_bundled(self.probe(sys.executable, str(archive), cwd=self.tmp), self.tmp / "cache" / "aidd")

    # It builds with the hash-locked backend, so it runs where that is allowed: ci.yml's test job sets BUILD_WHEEL_TEST=1.
    @unittest.skipUnless(shutil.which("uv") and os.environ.get("BUILD_WHEEL_TEST") == "1", "set BUILD_WHEEL_TEST=1 with uv on PATH to build a wheel")
    def test_an_installed_wheel_reads_its_own_data(self):
        constraint = ROOT / ".github" / "requirements" / "build.txt"
        build = ["uv", "build", "--wheel", "-o", str(self.tmp / "dist"), "--build-constraint", str(constraint), "--require-hashes"]
        subprocess.run(build, cwd=ROOT, check=True, capture_output=True, timeout=600)
        (wheel,) = (self.tmp / "dist").glob("*.whl")
        venv = self.tmp / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, capture_output=True, timeout=300)
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run([str(python), "-m", "pip", "install", "--quiet", "--no-index", "--no-deps", str(wheel)], check=True, capture_output=True, timeout=300)
        found = self.probe(str(python), cwd=self.tmp)
        self.assert_bundled(found, Path(found["package"]).resolve().parent)


if __name__ == "__main__":
    unittest.main()
