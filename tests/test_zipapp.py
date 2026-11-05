"""aidd.pyz: the whole CLI as one zipapp. It builds from this checkout with the standard library only, runs with no
install (`python aidd.pyz --version`, `aidd status`, `aidd new spec`), finds its bundled data inside the archive, and
builds reproducibly under SOURCE_DATE_EPOCH."""

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import zipfile
from pathlib import Path

from helpers import ROOT, git, make_repo

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

    def test_a_git_checkout_packs_only_what_git_tracks(self):
        # A local build someone shares must not carry a file git ignores, such as a secret in `.env.local`, as the wheel
        # carries none: from a git checkout, the build reads the file list from git.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "checkout"
            shutil.copytree(ROOT / "src" / "aidd", root / "src" / "aidd", ignore=pyz._SKIP)
            for rel in resources._LAYOUT.values():
                shutil.copytree(ROOT / rel, root / rel, ignore=pyz._SKIP)
            shutil.copy2(ROOT / ".gitignore", root / ".gitignore")
            git(root, "init", "-q")
            git(root, "add", "-A")
            (root / "src" / "aidd" / ".env.local").write_text("TOKEN=planted\n", encoding="utf-8")
            (root / "schemas" / "scratch-notes.md").write_text("not added\n", encoding="utf-8")
            out = pyz.build(Path(tmp) / "aidd.pyz", root)
            with zipfile.ZipFile(out) as zf:
                names = zf.namelist()
        self.assertNotIn("aidd/.env.local", names)
        self.assertNotIn("aidd/_data/schemas/scratch-notes.md", names)
        self.assertIn("aidd/cli/__init__.py", names)
        self.assertIn("aidd/_data/schemas/risks.json", names)

    def test_version_and_status_run_from_the_archive_alone(self):
        run = self.run_pyz("--version", cwd=self.dir)
        self.assertEqual((run.returncode, run.stdout.strip()), (0, f"aidd {__version__}"), run.stderr)
        scratch = make_repo(self.dir / "scratch", "team")
        run = self.run_pyz("status", cwd=scratch)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("nothing is open", run.stdout)
        # Bundled data (the Spec template, the schemas) comes out of the archive.
        run = self.run_pyz("new", "spec", "SPEC-1", "--title", "Greeting", cwd=scratch)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("\nid: SPEC-1\n", (scratch / "specs" / "SPEC-1.md").read_text(encoding="utf-8"))
        extracted = list((self.dir / "cache" / "aidd").glob("pyz-*/.complete"))
        self.assertEqual(len(extracted), 1)

    def test_the_work_page_renders_from_the_archive(self):
        # The page reads its design tokens, CSS, and script from the package, which inside the archive is no folder.
        scratch = make_repo(self.dir / "html", "team")
        run = self.run_pyz("status", "--html", cwd=scratch)
        self.assertEqual(run.returncode, 0, run.stderr)
        page = (scratch / ".aidd" / "views" / "status-work.html").read_text(encoding="utf-8")
        self.assertIn("<style", page)
        self.assertIn("<script", page)

    def test_an_exit_code_is_kept(self):
        run = self.run_pyz("validate", "missing.md", cwd=self.dir)
        self.assertNotEqual(run.returncode, 0)

    def test_it_is_reproducible_under_source_date_epoch(self):
        # Both builds read one frozen copy of the source, so a test in another process that writes into the checkout
        # between them never makes the archives differ.
        frozen = self.dir / "frozen"
        shutil.copytree(ROOT / "src" / "aidd", frozen / "src" / "aidd", ignore=pyz._SKIP)
        for rel in resources._LAYOUT.values():
            shutil.copytree(ROOT / rel, frozen / rel, ignore=pyz._SKIP)
        with mock.patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "1767225600"}):
            a = pyz.build(self.dir / "a" / "aidd.pyz", frozen).read_bytes()
            b = pyz.build(self.dir / "b" / "aidd.pyz", frozen).read_bytes()
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

    def test_the_extractor_reads_no_archive_or_member_past_its_cap(self):
        big = self.dir / "big.pyz"
        with zipfile.ZipFile(big, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("aidd/_data/schemas/a.json", "x" * 100)
        with (
            mock.patch.dict(os.environ, {"XDG_CACHE_HOME": str(self.dir / "capcache")}),
            mock.patch.object(resources, "MAX_MEMBER_BYTES", 10),
            self.assertRaisesRegex(ValueError, "larger than 10 bytes"),
        ):
            resources._extracted(big)
        many = self.dir / "many.pyz"
        with zipfile.ZipFile(many, "w") as zf:
            for i in range(5):
                zf.writestr(f"aidd/_data/schemas/{i}.json", "x" * 40)
        with (
            mock.patch.dict(os.environ, {"XDG_CACHE_HOME": str(self.dir / "capcache")}),
            mock.patch.object(resources, "MAX_TOTAL_BYTES", 100),
            self.assertRaisesRegex(ValueError, "larger than 100 bytes in all"),
        ):
            resources._extracted(many)  # each member is small, and together they are not
        other = self.dir / "other.pyz"
        other.write_bytes(big.read_bytes())
        with (
            mock.patch.dict(os.environ, {"XDG_CACHE_HOME": str(self.dir / "capcache")}),
            mock.patch.object(resources, "MAX_ARCHIVE_BYTES", 10),
            self.assertRaisesRegex(ValueError, "larger than 10 bytes"),
        ):
            resources._extracted(other)

    def test_a_new_extraction_removes_the_folders_no_zipapp_has_used_for_two_weeks(self):
        cache = self.dir / "prunecache"
        # Named as `_extracted` names its folders, and one that is not: the cleanup removes only its own.
        old, recent, other = (cache / "aidd" / name for name in ("pyz-" + "a" * 24, "pyz-" + "b" * 24, "pyz-mine"))
        for folder in (old, recent, other):
            folder.mkdir(parents=True)
            (folder / ".complete").write_text("x\n", encoding="utf-8")
        weeks_ago = time.time() - resources.STALE_EXTRACTED_SECONDS - 60
        for folder in (old, other):
            os.utime(folder / ".complete", (weeks_ago, weeks_ago))
        new = self.dir / "new.pyz"
        with zipfile.ZipFile(new, "w") as zf:
            zf.writestr("aidd/_data/schemas/a.json", "{}")
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": str(cache)}):
            dest = resources._extracted(new)
            self.assertEqual(sorted(p.name for p in (cache / "aidd").iterdir()), sorted([dest.name, recent.name, other.name]))
            os.utime(dest / ".complete", (weeks_ago, weeks_ago))
            resources._extracted.cache_clear()
            self.assertEqual(resources._extracted(new), dest)
        self.assertGreater((dest / ".complete").stat().st_mtime, weeks_ago, "a zipapp in use keeps its folder fresh")


if __name__ == "__main__":
    unittest.main()
