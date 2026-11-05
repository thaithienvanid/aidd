"""install.sh: which refs it accepts, how a release tag's wheel is checked before anything installs, and which Python
each install path needs. aidd is not on PyPI, so a tag installs the wheel of its GitHub Release. Every tool it calls is
a fake; the release is a folder the test serves as AIDD_RELEASE_URL, and the fake Pythons run the installer's check
with the real interpreter."""

import hashlib
import http.server
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
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
# A proxy on a closed port, so a git call made in a test reaches no host.
NO_NETWORK = {"HTTPS_PROXY": "http://127.0.0.1:1", "https_proxy": "http://127.0.0.1:1"}
GITHUB_RELEASES = "https://github.com/thaithienvanid/aidd/releases/download"
# What the installer puts before `ls-remote`: https alone, each other protocol named, so a repository cannot allow one.
GIT_FLAGS = (
    "-c credential.helper= -c core.askPass= -c protocol.allow=never -c protocol.https.allow=always -c protocol.http.allow=never -c protocol.ssh.allow=never "
    "-c protocol.git.allow=never -c protocol.file.allow=never -c protocol.ext.allow=never"
)


def python_reaching(base: str) -> str:
    """A Python 3.11+ whose check reads the releases from `base` where the installer asks GitHub's, so a test of the
    default install (no mirror) never touches the network. Its arguments: -I - version base dest pinned soft."""
    return (
        f'if [ "$1 $2" = "-I -" ]; then\n  base="$4"\n  [ "$base" = "{GITHUB_RELEASES}" ] && base="{base}"\n'
        f'  exec "{sys.executable}" -I - "$3" "$base" "$5" "$6" "$7"\nfi\nexit 0'
    )


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
        # One log for the class, emptied for each test, so a fake's text (which names it) is the same in every test.
        # A shell fake is a link to the one shared shim whatever its text; the same text matters for a fake that is not one.
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

    def uv_with_python(self, python: str = WHEEL_PYTHON) -> None:
        # The system Python is 3.9: uv finds (or brings) the 3.11+ that checks the wheel.
        self.fake("uvpython", python)
        self.fake("uv", 'case "$1 $2" in "python find") echo "$(dirname "$0")/uvpython";; esac')  # uvpython in self.bin

    def install(self, cwd: Path | None = None, mirror: bool = True, **env: str) -> subprocess.CompletedProcess:
        home = self.dir / "home"
        home.mkdir(exist_ok=True)
        full = {"PATH": os.pathsep.join([str(self.bin), self.system]), "HOME": str(home), "TMPDIR": str(self.dir)}
        # The test's release folder is a mirror, which needs a wheel digest from elsewhere: the test's own, unless a test
        # sets AIDD_SHA256 itself (an empty one asks for none).
        if mirror:
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

    def test_the_default_ref_is_this_release_when_it_is_out(self):
        self.uv_with_python()
        self.fake("git", "exit 1")  # logs a call
        self.release(__version__)
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        [cmd] = self.installs("uv")
        self.assertTrue(cmd.endswith(f"/aidd-{__version__}-py3-none-any.whl"), cmd)
        self.assertFalse([c for c in self.called() if c.startswith("git ")], "a release that is out never asks for main")

    def test_a_named_release_that_is_not_out_names_a_commit_to_build_from(self):
        self.uv_with_python()
        r = self.install(AIDD_REF="v1.2.3")
        self.assertEqual(r.returncode, 1)
        self.assertIn("release has no aidd-", r.stderr)
        self.assertIn("Before the first release, set AIDD_REF to a full commit SHA", r.stderr)
        self.assertIn("git ls-remote https://github.com/thaithienvanid/aidd refs/heads/main", r.stderr)
        self.assertEqual(self.installs("uv"), [], "nothing is installed")

    def no_release_install(self, base: str | None = None, cwd: Path | None = None, **env: str) -> subprocess.CompletedProcess:
        """The default install while this release is not out: no AIDD_REF, no mirror, and no digest to match. GitHub's
        releases are `base` (default: the test's empty release folder, so every wheel is a 404)."""
        self.uv_with_python(python_reaching(base or self.releases.as_uri()))
        self.releases.mkdir(exist_ok=True)
        return self.install(cwd=cwd, mirror=False, AIDD_SHA256="", **env)

    def git_listing(self, tags: str = "") -> None:
        """A git whose ls-remote lists `tags` (lines of `<sha>\\trefs/tags/...`) and main's commit."""
        self.fake("git", f"case \"$*\" in *--tags*) printf '{tags}';; *) printf '{COMMIT}\\trefs/heads/main\\n';; esac")

    def test_with_no_ref_and_no_release_it_builds_main_at_one_commit_and_says_so(self):
        self.git_listing()
        r = self.no_release_install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"No release of aidd is out yet, so this is unreleased code built from main at {COMMIT}, with no SHA256SUMS or provenance", r.stdout)
        self.assertEqual(self.installs("uv"), [f"uv tool install --force --python >=3.11 git+https://github.com/thaithienvanid/aidd@{COMMIT}"])
        self.assertEqual(
            [c for c in self.called() if c.startswith("git ")],
            [
                f"git {GIT_FLAGS} ls-remote --tags https://github.com/thaithienvanid/aidd",
                f"git {GIT_FLAGS} ls-remote https://github.com/thaithienvanid/aidd refs/heads/main",
            ],
        )

    def test_the_git_calls_run_away_from_the_current_repository_and_allow_https_only(self):
        """A repository's config (an `insteadOf` to an `ext::` URL, with `protocol.ext.allow=always`) runs a command on a
        `git ls-remote` made inside it; the installer makes its calls from its own folder, so it does not."""
        real_git = shutil.which("git", path="/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin")
        if real_git is None:
            self.skipTest("git is required")
        marker = self.dir / "ran"
        repo = self.dir / "someone-elses-checkout"
        repo.mkdir()
        subprocess.run([real_git, "init", "-q", str(repo)], check=True, capture_output=True)
        for key, value in (
            (f"url.ext::sh -c touch% {marker}.insteadOf", "https://github.com/thaithienvanid/aidd"),
            ("protocol.ext.allow", "always"),
        ):
            subprocess.run([real_git, "-C", str(repo), "config", key, value], check=True, capture_output=True)
        url = "https://github.com/thaithienvanid/aidd"
        subprocess.run([real_git, "ls-remote", url], cwd=repo, capture_output=True, timeout=30, check=False, stdin=subprocess.DEVNULL)
        self.assertTrue(marker.exists(), "the control: git itself runs the command from inside that repository")
        marker.unlink()
        self.fake("git", f'exec "{real_git}" "$@"')
        self.fake("curl", "exit 22")
        r = self.no_release_install(cwd=repo, GIT_DIR=str(repo / ".git"), **NO_NETWORK)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertFalse(marker.exists(), "the repository's config ran a command")
        self.assertEqual(self.installs("uv"), [])

    def test_the_git_calls_do_not_read_the_current_repository_s_config(self):
        real_git = shutil.which("git", path="/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin")
        if real_git is None:
            self.skipTest("git is required")
        repo = self.dir / "someone-elses-checkout"
        repo.mkdir()
        subprocess.run([real_git, "init", "-q", str(repo)], check=True, capture_output=True)
        # The repository sends the GitHub URL to another host.
        subprocess.run([real_git, "-C", str(repo), "config", "url.https://rewritten.invalid/.insteadOf", "https://github.com/thaithienvanid/aidd"], check=True)
        self.fake("git", f'exec "{real_git}" "$@"')
        self.fake("curl", "exit 22")
        trace = self.dir / "trace"
        env = {"GIT_DIR": str(repo / ".git"), "GIT_TRACE": str(trace), **NO_NETWORK}
        r = self.no_release_install(cwd=repo, **env)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("ls-remote", trace.read_text(encoding="utf-8"), "git ran, and traced")
        self.assertNotIn("rewritten.invalid", trace.read_text(encoding="utf-8"), "the repository's config was read")

    def test_a_ref_that_only_ends_in_main_is_not_main(self):
        self.fake("git", f"case \"$*\" in *--tags*) ;; *) printf '{'f' * 40}\\trefs/heads/a/refs/heads/main\\n{COMMIT}\\trefs/heads/main\\n';; esac")
        r = self.no_release_install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"built from main at {COMMIT}", r.stdout)

    def test_without_git_the_commit_of_main_comes_from_github_s_api(self):
        self.fake("git", "exit 1")
        self.fake("curl", f"case \"$*\" in *matching-refs*) echo '[]';; *) echo {COMMIT};; esac")
        r = self.no_release_install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"built from main at {COMMIT}", r.stdout)
        self.assertTrue(any(c.startswith("curl ") and "api.github.com/repos/thaithienvanid/aidd/commits/main" in c for c in self.called()), self.called())
        self.assertEqual(len(self.installs("uv")), 1)

    def test_when_main_s_commit_cannot_be_read_nothing_is_installed(self):
        self.fake("git", 'case "$*" in *--tags*) ;; *) exit 1;; esac')
        self.fake("curl", "exit 22")
        r = self.no_release_install()
        self.assertEqual(r.returncode, 1)
        self.assertIn("main's commit could not be read", r.stderr)
        self.assertEqual(self.installs("uv"), [])

    def test_a_release_that_exists_is_never_replaced_by_main(self):
        """The release PR's window: the default ref is bumped, the Release is not published yet, and the tag may exist."""
        self.git_listing(tags=f"{'a' * 40}\\trefs/tags/v1.0.0\\n{'b' * 40}\\trefs/tags/v1.0.0^{{}}\\n")
        r = self.no_release_install()
        self.assertEqual(r.returncode, 1)
        self.assertIn("the project has published a release: try again in a few minutes, or set AIDD_REF", r.stderr)
        self.assertNotIn("No release of aidd is out yet", r.stdout)
        self.assertEqual(self.installs("uv"), [])
        self.assertFalse([c for c in self.called() if c.endswith("refs/heads/main")], "main's commit is never asked for")

    def test_when_nothing_can_say_whether_a_release_exists_nothing_is_installed(self):
        self.fake("git", "exit 1")
        self.fake("curl", "exit 22")
        r = self.no_release_install()
        self.assertEqual(r.returncode, 1)
        self.assertIn("neither git nor GitHub's API could say whether any release exists", r.stderr)
        self.assertEqual(self.installs("uv"), [])

    def test_a_mirror_that_answers_404_never_falls_back_to_main(self):
        self.git_listing()  # no tag exists, so only the mirror stops the fallback
        self.uv_with_python()
        self.fake("gh")
        r = self.install(AIDD_SHA256="")  # a mirror, no digest, gh on PATH, and no release in the mirror
        self.assertEqual(r.returncode, 1)
        self.assertIn("release has no aidd-", r.stderr)
        self.assertNotIn("No release of aidd is out yet", r.stdout)
        self.assertEqual(self.installs("uv"), [])
        self.assertFalse([c for c in self.called() if c.startswith("git ")], "a mirror's 404 never asks git or GitHub")

    def test_a_server_error_or_an_unreachable_source_refuses_and_never_falls_back(self):
        """Only a 404 means the release is missing. A 500 and a refused connection are failures, with no release question."""
        self.git_listing()  # no tag exists: the fallback is open, so only the error handling stops it
        server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), type("Fails", (http.server.BaseHTTPRequestHandler,), {"do_GET": lambda h: h.send_error(500), "log_message": lambda *a: None})
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        refused = socket.socket()
        refused.bind(("127.0.0.1", 0))
        closed_port = refused.getsockname()[1]
        refused.close()
        for base, said in ((f"http://127.0.0.1:{server.server_address[1]}", "answered 500"), (f"http://127.0.0.1:{closed_port}", "could not reach")):
            with self.subTest(said=said):
                self.calls.unlink(missing_ok=True)
                r = self.no_release_install(base)
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertIn(said, r.stderr)
                self.assertNotIn("No release of aidd is out yet", r.stdout)
                self.assertEqual(self.installs("uv"), [])
                self.assertFalse([c for c in self.called() if c.startswith("git ")], "an error is not a missing release")

    def test_a_digest_asks_for_a_release_so_main_never_stands_in(self):
        self.uv_with_python()
        self.git_listing()
        r = self.install()  # AIDD_SHA256 is set
        self.assertEqual(r.returncode, 1)
        self.assertIn("release has no aidd-", r.stderr)
        self.assertEqual(self.installs("uv"), [])

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
            r"^gh attestation verify \S+/aidd-1\.2\.3-py3-none-any\.whl --repo thaithienvanid/aidd --source-ref refs/tags/v1\.2\.3 --signer-workflow thaithienvanid/aidd/\.github/workflows/release\.yml$",
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

    def test_without_gh_the_installer_says_the_provenance_went_unchecked_and_still_installs(self):
        self.uv_with_python()
        self.release()
        r = self.install(AIDD_REF="v1.2.3")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("against the v1.2.3 release's SHA256SUMS", r.stdout)
        self.assertIn("gh is not installed, so the build provenance was not checked, but the wheel matched SHA256SUMS", r.stdout)
        self.assertIn("install gh (https://cli.github.com)", r.stdout)
        self.assertEqual(len(self.installs("uv")), 1)

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
