"""install.sh: which refs it accepts, how a release tag's wheel is checked before anything installs, and which Python
each install path needs. aidd is not on PyPI, so a tag installs the wheel of its GitHub Release. Every tool it calls is
a fake; the release is a folder the test serves as AIDD_RELEASE_URL, and the fake Pythons run the installer's check
with the real interpreter."""

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, write_executable

from aidd import __version__

INSTALLER = ROOT / "install.sh"
COMMIT = "0123456789abcdef0123456789abcdef01234567"
WHEEL = b"a wheel"
WHEEL_SHA256 = hashlib.sha256(WHEEL).hexdigest()

# A Python 3.11+: the installer's inline download and check (`python -I - <args>`) runs on the real interpreter.
WHEEL_PYTHON = f'[ "$1 $2" = "-I -" ] && exec "{sys.executable}" "$@"\nexit 0'


@unittest.skipIf(os.name == "nt" or not shutil.which("sh"), "install.sh is a POSIX shell script")
class InstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.shared.cleanup)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.bin = self.dir / "bin"
        self.bin.mkdir()
        self.releases = self.dir / "releases"
        # One log for the class, emptied for each test, so a fake's text (which names it) is the same in every test
        # and `write_executable` keeps one file for it.
        self.calls = Path(self.shared.name) / "calls.log"
        self.calls.unlink(missing_ok=True)
        # The basic utilities only; no uv, pipx, gh, or aidd unless a test adds a fake.
        self.system = os.pathsep.join(dict.fromkeys([str(Path(shutil.which("sh") or "/bin/sh").parent), "/usr/bin", "/bin"]))
        for tool in ("uv", "pipx", "aidd"):
            if shutil.which(tool, path=self.system):
                self.skipTest(f"{tool} is installed in a system directory")
        if shutil.which("gh", path=self.system):
            self.fake("gh")  # a runner's own gh, which would ask GitHub: one that accepts every wheel stands in for it
        # A Python 3.9, as stock macOS ships: every interpreter name the installer may try is too old.
        for name in ("python3.15", "python3.14", "python3.13", "python3.12", "python3.11", "python3", "python"):
            self.fake(name, 'case "$1" in --version) echo "Python 3.9.6";; esac\nexit 1')

    def tearDown(self):
        self.tmp.cleanup()

    def fake(self, name: str, body: str = "") -> None:
        write_executable(self.bin / name, f'#!/bin/sh\necho "{name} $*" >> "{self.calls}"\n{body}\n')

    def release(self, version: str = "1.2.3", wheel: bytes = WHEEL, listed: str | None = None) -> None:
        """The GitHub Release of v`version`: its wheel, and SHA256SUMS listing `listed` (the wheel's own digest by default)."""
        folder = self.releases / f"v{version}"
        folder.mkdir(parents=True)
        name = f"aidd-{version}-py3-none-any.whl"
        (folder / name).write_bytes(wheel)
        digest = hashlib.sha256(wheel).hexdigest() if listed is None else listed
        (folder / "SHA256SUMS").write_text(f"{digest}  {name}\n{'1' * 64}  aidd.pyz\n" if digest else f"{'1' * 64}  aidd.pyz\n", encoding="utf-8")

    def uv_with_python(self) -> None:
        # The system Python is 3.9: uv finds (or brings) the 3.11+ that checks the wheel.
        self.fake("uvpython", WHEEL_PYTHON)
        self.fake("uv", 'case "$1 $2" in "python find") echo "$(dirname "$0")/uvpython";; esac')  # uvpython in self.bin

    def install(self, cwd: Path | None = None, **env: str) -> subprocess.CompletedProcess:
        home = self.dir / "home"
        home.mkdir(exist_ok=True)
        full = {"PATH": os.pathsep.join([str(self.bin), self.system]), "HOME": str(home), "TMPDIR": str(self.dir)}
        # The test's release folder is a mirror, which needs a wheel digest from elsewhere: the test's own, unless a test
        # sets AIDD_SHA256 itself (an empty one asks for none).
        full["AIDD_RELEASE_URL"] = self.releases.as_uri()
        if env.get("AIDD_REF") != COMMIT:  # a commit builds from source, which takes no wheel digest
            full["AIDD_SHA256"] = WHEEL_SHA256
        return subprocess.run(["sh", str(INSTALLER)], env={**full, **env}, cwd=cwd, capture_output=True, text=True, timeout=30, encoding="utf-8")

    def called(self) -> list[str]:
        return self.calls.read_text(encoding="utf-8").splitlines() if self.calls.exists() else []

    def installs(self, tool: str) -> list[str]:
        return [c for c in self.called() if c.startswith(f"{tool} ") and " install " in f" {c} "]

    def test_only_a_release_tag_or_a_full_commit_is_accepted(self):
        self.fake("uv")
        for bad in ("v1.0", "v1.0.0.1", "v1.0.0-rc1", "1.0.0", "vX.Y.Z", "v1.0.0\nv2.0.0", "main", "abc123"):
            r = self.install(AIDD_REF=bad)
            self.assertEqual(r.returncode, 1, bad)
            self.assertIn("AIDD_REF must be a vX.Y.Z release tag or a full commit SHA", r.stderr, bad)
        self.assertFalse([c for c in self.called() if c.startswith("uv ")])

    def test_a_tag_installs_its_release_wheel_once_it_matches_the_release_sha256sums(self):
        self.uv_with_python()
        self.release()
        r = self.install(AIDD_REF="v1.2.3")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("verified aidd-1.2.3-py3-none-any.whl against the v1.2.3 release's SHA256SUMS", r.stdout)
        [cmd] = self.installs("uv")
        self.assertTrue(cmd.startswith("uv tool install --force --python >=3.11 --no-build "), cmd)
        self.assertTrue(cmd.endswith("/aidd-1.2.3-py3-none-any.whl"), cmd)
        self.assertIn("installed; open a new shell", r.stdout)
        self.assertFalse([c for c in self.called() if " pip " in f" {c} "], "no package index is asked")

    def test_a_module_planted_in_the_current_folder_never_runs(self):
        """Run from inside a checkout someone else wrote, the installer's Pythons run isolated (`-I`), so a `hashlib.py`
        or `venv.py` there is never imported."""
        self.uv_with_python()
        self.release()
        here = self.dir / "someone-elses-checkout"
        here.mkdir()
        marker = self.dir / "planted-ran"
        for name in ("hashlib", "urllib", "venv", "ensurepip", "pip"):
            (here / f"{name}.py").write_text(f"open({str(marker)!r}, 'w').write('{name}')\n", encoding="utf-8")
        r = self.install(cwd=here, AIDD_REF="v1.2.3", PYTHONPATH=str(here))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(marker.exists(), "a planted module ran")
        pythons = [c for c in self.called() if c.startswith(("uvpython ", "python"))]
        self.assertTrue(pythons and all(c.split()[1] == "-I" for c in pythons), pythons)

    def test_the_default_ref_is_this_release(self):
        self.uv_with_python()
        self.release(__version__)
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        [cmd] = self.installs("uv")
        self.assertTrue(cmd.endswith(f"/aidd-{__version__}-py3-none-any.whl"), cmd)

    def test_before_the_release_a_tag_names_a_commit_to_build_from(self):
        self.uv_with_python()
        for env in ({}, {"AIDD_REF": "v1.2.3"}):
            r = self.install(**env)
            self.assertEqual(r.returncode, 1, env)
            self.assertIn("release has no aidd-", r.stderr)
            self.assertIn("Before the first release, set AIDD_REF to a full commit SHA", r.stderr)
            self.assertIn("git ls-remote https://github.com/thaithienvanid/aidd refs/heads/main", r.stderr)
        self.assertEqual(self.installs("uv"), [], "nothing is installed")

    def test_a_wheel_that_does_not_match_is_never_installed(self):
        self.uv_with_python()
        cases = (
            ({"listed": "0" * 64}, {}, "does not match the v1.2.3 release's SHA256SUMS"),
            ({"listed": ""}, {}, "SHA256SUMS does not list aidd-1.2.3-py3-none-any.whl"),
            ({}, {"AIDD_SHA256": "0" * 64}, "does not match AIDD_SHA256"),
        )
        for release, env, said in cases:
            with self.subTest(said=said):
                shutil.rmtree(self.releases, ignore_errors=True)
                self.release(**release)
                r = self.install(AIDD_REF="v1.2.3", **env)
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertIn(said, r.stderr)
                self.assertEqual(self.installs("uv"), [])
        shutil.rmtree(self.releases)
        self.release()
        r = self.install(AIDD_REF="v1.2.3", AIDD_SHA256=WHEEL_SHA256.upper())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("against the v1.2.3 release's SHA256SUMS and AIDD_SHA256", r.stdout)

    def test_with_gh_the_build_provenance_is_verified_before_any_install(self):
        self.uv_with_python()
        self.release()
        self.fake("gh")
        r = self.install(AIDD_REF="v1.2.3")
        self.assertEqual(r.returncode, 0, r.stderr)
        [verify] = [c for c in self.called() if c.startswith("gh ")]
        self.assertRegex(
            verify,
            r"^gh attestation verify \S+/aidd-1\.2\.3-py3-none-any\.whl --repo thaithienvanid/aidd --signer-workflow thaithienvanid/aidd/\.github/workflows/release\.yml$",
        )
        self.assertIn("gh verified its build provenance", r.stdout)
        refused = 'case "$1 $2" in "attestation verify") exit 1;; esac\nexit 0'
        signed_out = 'case "$1 $2" in "attestation verify"|"auth status") exit 1;; esac\nexit 0'
        for body, said in (
            (refused, "gh attestation verify refused aidd-1.2.3-py3-none-any.whl, so nothing was installed"),
            (signed_out, "it is not signed in: run gh auth login"),
            ("exit 1", "this gh has no attestation command"),
        ):
            with self.subTest(said=said):
                self.calls.unlink(missing_ok=True)
                self.fake("gh", body)
                r = self.install(AIDD_REF="v1.2.3")
                self.assertEqual(r.returncode, 1)
                self.assertIn(said, r.stderr)
                self.assertEqual(self.installs("uv"), [])

    def test_a_mirror_proves_nothing_alone_and_only_https_or_a_local_copy_counts(self):
        if shutil.which("gh", path=self.system):
            self.skipTest("a system gh would verify the wheel")
        self.uv_with_python()
        self.release()
        r = self.install(AIDD_REF="v1.2.3", AIDD_SHA256="")
        self.assertEqual(r.returncode, 1)
        self.assertIn("a mirror's SHA256SUMS can't prove where its wheel came from: set AIDD_SHA256", r.stderr)
        self.assertEqual(self.called(), [], "nothing is downloaded or installed")
        for url in ("http://mirror.example/releases", "ftp://mirror.example", "mirror.example"):
            r = self.install(AIDD_REF="v1.2.3", AIDD_RELEASE_URL=url)
            self.assertEqual(r.returncode, 1, url)
            self.assertIn("AIDD_RELEASE_URL must start with https://", r.stderr, url)

    def test_a_commit_builds_from_source_with_uv(self):
        self.fake("uv")
        r = self.install(AIDD_REF=COMMIT)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"uv tool install --force --python >=3.11 git+https://github.com/thaithienvanid/aidd@{COMMIT}", self.called())
        self.assertIn("AIDD_SHA256 applies to a release wheel", self.install(AIDD_REF=COMMIT, AIDD_SHA256=WHEEL_SHA256).stderr)

    def test_pipx_gets_an_explicit_python_3_11_or_later(self):
        self.fake("pipx")
        self.fake("python3.12", WHEEL_PYTHON)
        self.release()
        r = self.install(AIDD_REF="v1.2.3")
        self.assertEqual(r.returncode, 0, r.stderr)
        [cmd] = self.installs("pipx")
        self.assertTrue(cmd.startswith(f"pipx install --force --python {self.bin / 'python3.12'} --pip-args=--only-binary=:all: "), cmd)
        self.assertTrue(cmd.endswith("/aidd-1.2.3-py3-none-any.whl"), cmd)

    def test_without_uv_an_old_python_is_a_clear_error(self):
        self.fake("pipx")
        r = self.install(AIDD_REF=COMMIT)
        self.assertEqual(r.returncode, 1)
        self.assertIn("needs Python 3.11 or later (found: Python 3.9.6)", r.stderr)
        self.assertIn("Install uv", r.stderr)
        self.assertFalse([c for c in self.called() if c.startswith("pipx ")])
        self.release()
        self.assertIn("checking the release wheel needs Python 3.11 or later", self.install(AIDD_REF="v1.2.3").stderr)

    def test_a_missing_venv_module_is_a_clear_error(self):
        # Python 3.12 without ensurepip, as Debian ships it without python3-venv.
        self.fake("python3.12", 'case "$*" in *ensurepip*) exit 1;; esac\nexit 0')
        r = self.install(AIDD_REF=COMMIT)
        self.assertEqual(r.returncode, 1)
        self.assertIn("the venv module is not available", r.stderr)
        self.assertIn("apt install python3-venv", r.stderr)

    def test_a_missing_pip_in_the_venv_is_a_clear_error(self):
        self.fake("python3.12", 'case "$*" in *"-m pip"*) exit 1;; esac\nexit 0')
        r = self.install(AIDD_REF=COMMIT)
        self.assertEqual(r.returncode, 1)
        self.assertIn("pip is not available", r.stderr)


if __name__ == "__main__":
    unittest.main()
