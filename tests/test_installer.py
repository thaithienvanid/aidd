"""install.sh: which refs it accepts, when a release tag needs a pinned wheel, and which Python each install path
needs. Every tool it calls is a fake; the fake Pythons hash the downloaded wheel with the real interpreter."""

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd import __version__

INSTALLER = ROOT / "install.sh"
COMMIT = "0123456789abcdef0123456789abcdef01234567"
WHEEL = b"a wheel"  # what the fake `pip download` writes
WHEEL_SHA256 = hashlib.sha256(WHEEL).hexdigest()

# A Python 3.11+ with pip: `pip download` writes WHEEL as aidd-X.Y.Z-py3-none-any.whl into --dest, and the
# installer's inline check (`python - <wheel> <sha256>`) runs on the real interpreter.
WHEEL_PYTHON = f"""case "$1 $2 $3" in
  "-m pip download")
    dest=""; prev=""; last=""
    for a in "$@"; do [ "$prev" = "--dest" ] && dest="$a"; prev="$a"; last="$a"; done
    printf '%s' '{WHEEL.decode()}' > "$dest/aidd-${{last#aidd==}}-py3-none-any.whl"
    exit 0;;
esac
[ "$1" = "-" ] && exec "{sys.executable}" "$@"
exit 0"""


@unittest.skipIf(os.name == "nt" or not shutil.which("sh"), "install.sh is a POSIX shell script")
class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.bin = self.dir / "bin"
        self.bin.mkdir()
        self.calls = self.dir / "calls.log"
        # The basic utilities only; no uv, pipx, or aidd unless a test adds a fake.
        self.system = os.pathsep.join(dict.fromkeys([str(Path(shutil.which("sh") or "/bin/sh").parent), "/usr/bin", "/bin"]))
        for tool in ("uv", "pipx", "aidd"):
            if shutil.which(tool, path=self.system):
                self.skipTest(f"{tool} is installed in a system directory")
        # A Python 3.9, as stock macOS ships: every interpreter name the installer may try is too old.
        for name in ("python3.15", "python3.14", "python3.13", "python3.12", "python3.11", "python3", "python"):
            self.fake(name, 'case "$1" in --version) echo "Python 3.9.6";; esac\nexit 1')

    def tearDown(self):
        self.tmp.cleanup()

    def fake(self, name: str, body: str = "") -> None:
        path = self.bin / name
        path.write_text(f'#!/bin/sh\necho "{name} $*" >> "{self.calls}"\n{body}\n', encoding="utf-8")
        path.chmod(0o755)

    def install(self, script: Path = INSTALLER, **env: str) -> subprocess.CompletedProcess:
        home = self.dir / "home"
        home.mkdir(exist_ok=True)
        full = {"PATH": os.pathsep.join([str(self.bin), self.system]), "HOME": str(home), "TMPDIR": str(self.dir), **env}
        return subprocess.run(["sh", str(script)], env=full, capture_output=True, text=True, timeout=30, encoding="utf-8")

    def published(self) -> Path:
        """The installer as the release will ship it, once aidd is on PyPI."""
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertEqual(text.count('\nPUBLISHED=""\n'), 1, "install.sh must hold exactly one empty PUBLISHED line until the release")
        copy = self.dir / "install-published.sh"
        copy.write_text(text.replace('\nPUBLISHED=""\n', '\nPUBLISHED="yes"\n'), encoding="utf-8")
        return copy

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

    def test_before_the_release_a_tag_installs_only_a_pinned_wheel(self):
        self.fake("uv")
        for env in ({}, {"AIDD_REF": "v1.2.3"}):
            r = self.install(**env)
            self.assertEqual(r.returncode, 1, env)
            self.assertIn("aidd is not published on PyPI yet", r.stderr)
            self.assertIn("AIDD_REF to a full commit SHA", r.stderr)
            self.assertIn("AIDD_SHA256", r.stderr)
        self.assertIn(f"v{__version__}", self.install().stderr)  # the default ref is this release
        self.assertEqual(self.called(), [], "nothing is downloaded or installed")

    def test_a_commit_builds_from_source_with_uv(self):
        self.fake("uv")
        r = self.install(AIDD_REF=COMMIT)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"uv tool install --force --python >=3.11 git+https://github.com/thaithienvanid/aidd@{COMMIT}", self.called())
        self.assertIn("AIDD_SHA256 applies to a release wheel", self.install(AIDD_REF=COMMIT, AIDD_SHA256=WHEEL_SHA256).stderr)

    def test_uv_installs_the_checked_wheel_without_a_new_enough_system_python(self):
        # The system Python is 3.9: uv finds (or brings) the 3.11+ that checks the wheel, and installs it without building.
        self.fake("uvpython", WHEEL_PYTHON)
        self.fake("uv", f'case "$1 $2" in "python find") echo "{self.bin / "uvpython"}";; esac')
        r = self.install(AIDD_REF="v1.2.3", AIDD_SHA256=WHEEL_SHA256.upper())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("verified aidd-1.2.3-py3-none-any.whl against AIDD_SHA256", r.stdout)
        [cmd] = self.installs("uv")
        self.assertTrue(cmd.startswith("uv tool install --force --python >=3.11 --no-build "), cmd)
        self.assertTrue(cmd.endswith("/aidd-1.2.3-py3-none-any.whl"), cmd)
        self.assertIn("installed; open a new shell", r.stdout)

    def test_a_wheel_that_does_not_match_is_never_installed(self):
        self.fake("uvpython", WHEEL_PYTHON)
        self.fake("uv", f'case "$1 $2" in "python find") echo "{self.bin / "uvpython"}";; esac')
        r = self.install(AIDD_REF="v1.2.3", AIDD_SHA256="0" * 64)
        self.assertEqual(r.returncode, 1)
        self.assertIn("does not match AIDD_SHA256", r.stderr)
        self.assertEqual(self.installs("uv"), [])

    def test_once_published_the_default_ref_installs_this_release_by_name(self):
        self.fake("uv")
        r = self.install(self.published())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"uv tool install --force --python >=3.11 --no-build aidd=={__version__}", self.called())

    def test_pipx_gets_an_explicit_python_3_11_or_later(self):
        self.fake("pipx")
        self.fake("python3.12", WHEEL_PYTHON)
        r = self.install(AIDD_REF="v1.2.3", AIDD_SHA256=WHEEL_SHA256)
        self.assertEqual(r.returncode, 0, r.stderr)
        [cmd] = self.installs("pipx")
        self.assertTrue(cmd.startswith(f"pipx install --force --python {self.bin / 'python3.12'} --pip-args=--only-binary=:all: "), cmd)
        self.assertTrue(cmd.endswith("/aidd-1.2.3-py3-none-any.whl"), cmd)
        r = self.install(self.published(), AIDD_REF="v1.2.3")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"pipx install --force --python {self.bin / 'python3.12'} --pip-args=--only-binary=:all: aidd==1.2.3", self.called())

    def test_without_uv_an_old_python_is_a_clear_error(self):
        self.fake("pipx")
        r = self.install(AIDD_REF=COMMIT)
        self.assertEqual(r.returncode, 1)
        self.assertIn("needs Python 3.11 or later (found: Python 3.9.6)", r.stderr)
        self.assertIn("Install uv", r.stderr)
        self.assertFalse([c for c in self.called() if c.startswith("pipx ")])

    def test_a_missing_venv_module_is_a_clear_error(self):
        # Python 3.12 without ensurepip, as Debian ships it without python3-venv.
        self.fake("python3.12", 'case "$*" in *ensurepip*) exit 1;; esac\nexit 0')
        r = self.install(AIDD_REF=COMMIT)
        self.assertEqual(r.returncode, 1)
        self.assertIn("the venv module is not available", r.stderr)
        self.assertIn("apt install python3-venv", r.stderr)

    def test_a_missing_pip_is_a_clear_error_when_checking_the_wheel(self):
        self.fake("python3.12", 'case "$*" in *"-m pip"*) exit 1;; esac\nexit 0')
        r = self.install(AIDD_REF="v1.2.3", AIDD_SHA256="0" * 64)
        self.assertEqual(r.returncode, 1)
        self.assertIn("pip is not available", r.stderr)


if __name__ == "__main__":
    unittest.main()
