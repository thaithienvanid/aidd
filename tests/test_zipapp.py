"""aidd.pyz: the whole CLI as one zipapp. It builds from this checkout with the standard library only, runs with no
install (`python aidd.pyz --version`, `aidd list --branch`, `aidd new spec`), finds its bundled data inside the archive, and
builds reproducibly under SOURCE_DATE_EPOCH."""

import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from helpers import ROOT, make_repo

from aidd import __version__, pyz
from aidd.kernel import resources


def clean_env(**extra: str) -> dict[str, str]:
    """No PYTHONPATH: the archive alone must be enough."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH" and not k.startswith("AIDD_")}
    return env | extra


class ZipappTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name).resolve()
        cls.pyz = pyz.build(cls.dir / "out" / "aidd.pyz", ROOT)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_pyz(self, *args: str, cwd: Path) -> subprocess.CompletedProcess:
        env = clean_env(XDG_CACHE_HOME=str(self.dir / "cache"), HOME=str(self.dir / "home"))
        return subprocess.run([sys.executable, "-I", str(self.pyz), *args], cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", check=False)

    def test_it_holds_the_package_and_the_data_and_nothing_compiled(self):
        with zipfile.ZipFile(self.pyz) as zf:
            names = set(zf.namelist())
        self.assertIn("__main__.py", names)
        self.assertIn("aidd/cli/__init__.py", names)
        for name in resources._LAYOUT:
            self.assertTrue(any(n.startswith(f"aidd/_data/{name}/") for n in names), name)
        self.assertIn("aidd/_data/skill/assets/spec-short.md", names)
        self.assertFalse([n for n in names if "__pycache__" in n or n.endswith(".pyc")])
        self.assertTrue(self.pyz.read_bytes().startswith(b"#!/usr/bin/env python3\n"))

    def test_local_eval_results_are_never_bundled(self):
        # `claude plugin eval` writes plugins/aidd-team/evals/results/ (ignored by git); a build from a checkout
        # that has run the evals must not ship them.
        import shutil

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "checkout"
            shutil.copytree(ROOT / "src" / "aidd", root / "src" / "aidd", ignore=shutil.ignore_patterns("__pycache__"))
            for rel in resources._LAYOUT.values():
                shutil.copytree(ROOT / rel, root / rel, ignore=shutil.ignore_patterns("__pycache__", "results"))
            results = root / resources._LAYOUT["team"] / "evals" / "results"
            results.mkdir(parents=True)
            (results / "run-1.json").write_text("{}", encoding="utf-8")
            out = pyz.build(Path(tmp) / "aidd.pyz", root)
            with zipfile.ZipFile(out) as zf:
                names = zf.namelist()
        self.assertEqual([n for n in names if "/results/" in n], [])
        self.assertIn("aidd/cli/__init__.py", names)

    def test_version_and_list_run_from_the_archive_alone(self):
        run = self.run_pyz("--version", cwd=self.dir)
        self.assertEqual((run.returncode, run.stdout.strip()), (0, f"aidd {__version__}"), run.stderr)
        scratch = make_repo(self.dir / "scratch", "team")
        run = self.run_pyz("list", "--branch", cwd=scratch)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("Nothing is open", run.stdout)
        # Bundled data (the Spec template, the schemas) comes out of the archive.
        run = self.run_pyz("new", "spec", "SPEC-1", "--title", "Greeting", cwd=scratch)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("\nid: SPEC-1\n", (scratch / "specs" / "SPEC-1.md").read_text(encoding="utf-8"))
        extracted = list((self.dir / "cache" / "aidd").glob("pyz-*/.complete"))
        self.assertEqual(len(extracted), 1)

    def test_an_exit_code_is_kept(self):
        run = self.run_pyz("validate", "missing.md", cwd=self.dir)
        self.assertNotEqual(run.returncode, 0)

    def test_it_is_reproducible_under_source_date_epoch(self):
        old = os.environ.get("SOURCE_DATE_EPOCH")
        os.environ["SOURCE_DATE_EPOCH"] = "1767225600"
        try:
            a = pyz.build(self.dir / "a" / "aidd.pyz", ROOT).read_bytes()
            b = pyz.build(self.dir / "b" / "aidd.pyz", ROOT).read_bytes()
        finally:
            if old is None:
                os.environ.pop("SOURCE_DATE_EPOCH", None)
            else:
                os.environ["SOURCE_DATE_EPOCH"] = old
        self.assertEqual(a, b)

    def test_the_extractor_refuses_an_unsafe_member(self):
        bad = self.dir / "bad.pyz"
        with zipfile.ZipFile(bad, "w") as zf:
            zf.writestr("aidd/_data/../../escape.txt", "x")
        env_home = os.environ.get("XDG_CACHE_HOME")
        os.environ["XDG_CACHE_HOME"] = str(self.dir / "badcache")
        try:
            with self.assertRaises(ValueError):
                resources._extracted(bad)
        finally:
            if env_home is None:
                os.environ.pop("XDG_CACHE_HOME", None)
            else:
                os.environ["XDG_CACHE_HOME"] = env_home
        self.assertFalse((self.dir / "escape.txt").exists())


if __name__ == "__main__":
    unittest.main()
