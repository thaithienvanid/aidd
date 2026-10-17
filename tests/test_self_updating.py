"""`aidd self-update` and the daily check: releases only, installed from a verified wheel; the daily check only tells
unless the person opts in; main only when asked; a person at a terminal only; never a downgrade."""

import hashlib

import io
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from helpers import ROOT  # noqa: F401

from aidd.cli import app
from aidd.setup import self_updating as su

A = "a" * 40
B = "b" * 40
C = "c" * 40
PERSON = {"HOME": "/home/p"}


def tty():
    return True


class LatestTests(unittest.TestCase):
    def test_the_newest_release_tag_wins_by_version_not_by_name(self):
        refs = {"refs/tags/v1.2.0": A, "refs/tags/v1.10.0": B, "refs/heads/main": C}
        self.assertEqual(su.latest(refs), su.Target("v1.10.0", B, "1.10.0"))

    def test_an_annotated_tag_is_read_through_to_its_commit(self):
        refs = {"refs/tags/v1.0.0": A, "refs/tags/v1.0.0^{}": B, "refs/heads/main": C}
        self.assertEqual(su.latest(refs).sha, B)
        self.assertEqual(su.latest(dict(reversed(list(refs.items())))).sha, B)

    def test_main_only_when_asked(self):
        refs = {"refs/tags/v1.0.0-rc1": A, "refs/tags/nightly": B, "refs/heads/main": C}
        self.assertIsNone(su.latest(refs), "unreleased code is never a default target")
        self.assertEqual(su.latest(refs, main=True), su.Target("main", C, None))
        self.assertEqual(su.latest({**refs, "refs/tags/v1.0.0": A}, main=True), su.Target("main", C, None))

    def test_nothing_when_neither_is_there(self):
        self.assertIsNone(su.latest({"refs/heads/dev": A}))


class NeedsUpdateTests(unittest.TestCase):
    def test_a_newer_release_updates(self):
        self.assertTrue(su.needs_update(su.Target("v1.1.0", B, "1.1.0"), "1.0.0", A))
        self.assertTrue(su.needs_update(su.Target("v1.1.0", B, "1.1.0"), "1.0.0", None))

    def test_never_a_downgrade(self):
        self.assertFalse(su.needs_update(su.Target("v1.0.0", B, "1.0.0"), "1.1.0", A))

    def test_the_same_version_moves_a_source_build_onto_the_release_commit(self):
        self.assertTrue(su.needs_update(su.Target("v1.0.0", B, "1.0.0"), "1.0.0", A))
        self.assertFalse(su.needs_update(su.Target("v1.0.0", B, "1.0.0"), "1.0.0", B))
        self.assertFalse(su.needs_update(su.Target("v1.0.0", B, "1.0.0"), "1.0.0", None), "a wheel of the release is the release")

    def test_main_updates_on_any_other_commit(self):
        self.assertTrue(su.needs_update(su.Target("main", C, None), "1.0.0", A))
        self.assertFalse(su.needs_update(su.Target("main", C, None), "1.0.0", C))


class CommandTests(unittest.TestCase):
    def test_each_install_is_redone_the_way_it_was_made_from_its_source(self):
        want = "/cache/self-update/v1.1.0/aidd-1.1.0-py3-none-any.whl"
        with mock.patch.object(su.shutil, "which", side_effect=lambda name: f"/bin/{name}"):
            uv = su.update_command("uv", want)
            pipx = su.update_command("pipx", want)
        venv = su.update_command("venv", want)
        self.assertEqual(uv[:4], ["/bin/uv", "tool", "install", "--force"])
        self.assertEqual(pipx[:3], ["/bin/pipx", "install", "--force"])
        self.assertEqual(venv[1:4], ["-m", "pip", "install"])
        for cmd in (uv, pipx, venv):
            self.assertEqual(cmd[-1], want)

    def test_no_command_for_an_install_aidd_did_not_make(self):
        source = su.spec(su.Target("main", C, None))
        for kind in ("checkout", "pyz", "other"):
            self.assertIsNone(su.update_command(kind, source))
        with mock.patch.object(su.shutil, "which", return_value=None):
            self.assertIsNone(su.update_command("uv", source))
        for kind in ("checkout", "pyz", "uv", "other"):
            self.assertTrue(su.manual_hint(kind))

    def test_this_checkout_is_a_checkout(self):
        self.assertEqual(su.install_kind(), "checkout")


class AutoAllowedTests(unittest.TestCase):
    def test_a_person_at_a_terminal(self):
        self.assertTrue(su.auto_allowed("list", PERSON, tty))

    def test_never_without_a_terminal(self):
        self.assertFalse(su.auto_allowed("list", PERSON, lambda: False))

    def test_never_in_ci_an_agent_shell_a_hook_offline_or_turned_off(self):
        for extra in (
            {"CI": "true"},
            {"CLAUDECODE": "1"},
            {"CLAUDE_CODE_CHILD_SESSION": "1"},
            {"AI_AGENT": "x"},
            {"AIDD_AGENT": "1"},
            {"AIDD_OFFLINE": "1"},
            {"AIDD_HOOK_OFFLINE": "1"},
            {"AIDD_NO_AUTO_UPDATE": "1"},
        ):
            with self.subTest(extra):
                self.assertFalse(su.auto_allowed("list", {**PERSON, **extra}, tty))
        self.assertTrue(su.auto_allowed("list", {**PERSON, "CI": "false", "AIDD_NO_AUTO_UPDATE": "0"}, tty))

    def test_never_after_itself_a_hook_or_the_mcp_server(self):
        for command in (None, "self-update", "hook", "mcp"):
            self.assertFalse(su.auto_allowed(command, PERSON, tty))


RELEASE = su.Target("v1.1.0", B, "1.1.0")


class AutoUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patches = [
            mock.patch.object(su.resources, "cache_home", return_value=Path(self.tmp.name)),
            mock.patch.object(su, "auto_allowed", return_value=True),
            mock.patch.object(su, "install_kind", return_value="uv"),
            mock.patch.object(su, "installed_commit", return_value=A),
            mock.patch.object(su, "update_command", return_value=["uv", "tool", "install"]),
            mock.patch.object(su, "verified_wheel", return_value=(Path("/w.whl"), "its sha256 matches the release's SHA256SUMS")),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def run_once(self, target, code=0, now=None, auto=False):
        err = io.StringIO()
        env = {su.AUTO_ENV: "1" if auto else ""}
        with (
            mock.patch.object(su, "check", return_value=target) as check,
            mock.patch.object(su, "run_update", return_value=(code, "boom")) as run,
            mock.patch.dict(os.environ, env),
        ):
            with redirect_stderr(err):
                su.auto_update("list", now=now)
        return check, run, err.getvalue()

    def test_by_default_it_only_says_a_release_is_out(self):
        _, run, said = self.run_once(RELEASE)
        run.assert_not_called()
        self.assertIn("v1.1.0 is out", said)
        self.assertIn("`aidd self-update` installs it, checked against the release first", said)

    def test_with_the_opt_in_it_installs_the_verified_release_and_says_so(self):
        _, run, said = self.run_once(RELEASE, auto=True)
        run.assert_called_once()
        self.assertIn("updating from aidd", said)
        self.assertIn(f"updated to v1.1.0 ({B[:12]})", said)
        self.assertIn("SHA256SUMS", said)

    def test_a_release_that_fails_its_check_installs_nothing(self):
        with mock.patch.object(su, "verified_wheel", return_value=(None, "aidd-1.1.0-py3-none-any.whl does not match")):
            _, run, said = self.run_once(RELEASE, auto=True)
        run.assert_not_called()
        self.assertIn("not updated: aidd-1.1.0-py3-none-any.whl does not match", said)

    def test_at_most_once_a_day(self):
        now = time.time()
        self.run_once(RELEASE, now=now)
        check, run, said = self.run_once(RELEASE, now=now + 3600)
        check.assert_not_called()
        run.assert_not_called()
        self.assertEqual(said, "")
        check, _, _ = self.run_once(RELEASE, now=now + su.CHECK_EVERY_SECONDS + 1)
        check.assert_called_once()

    def test_silent_when_up_to_date_or_unreachable(self):
        for i, target in enumerate((su.Target("v1.1.0", A, "1.1.0"), None)):
            with mock.patch.object(su, "installed_commit", return_value=A), mock.patch.object(su, "__version__", "1.1.0"):
                _, run, said = self.run_once(target, now=time.time() + i * 2 * su.CHECK_EVERY_SECONDS)
            run.assert_not_called()
            self.assertEqual(said, "")

    def test_a_failure_keeps_the_old_cli_and_says_so(self):
        _, _, said = self.run_once(RELEASE, code=1, auto=True)
        self.assertIn("the update failed: boom", said)
        self.assertIn("`aidd self-update` tries again", said)

    def test_never_raises(self):
        with mock.patch.object(su, "check", side_effect=RuntimeError("no")):
            su.auto_update("list")

    def test_a_checkout_is_never_checked_and_another_install_is_only_told(self):
        with mock.patch.object(su, "install_kind", return_value="checkout"):
            check, _, _ = self.run_once(RELEASE)
        check.assert_not_called()
        with mock.patch.object(su, "install_kind", return_value="other"):
            _, run, said = self.run_once(RELEASE, now=time.time() + 3 * su.CHECK_EVERY_SECONDS, auto=True)
        run.assert_not_called()
        self.assertIn("v1.1.0 is out", said)


class VerifiedWheelTests(unittest.TestCase):
    """A release installs only from its own wheel, checked against the release's SHA256SUMS and, with gh, its provenance."""

    WHEEL = b"the wheel's bytes"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def fetch(self, sums: str, gh=None, gh_code=0):
        name = su.wheel_name("1.1.0")

        def get(url, **kw):
            return sums.replace("NAME", name).encode() if url.endswith("SHA256SUMS") else self.WHEEL

        done = mock.Mock(returncode=gh_code, stdout="", stderr="no attestation found")
        with (
            mock.patch.object(su.http, "get_bytes", side_effect=get) as got,
            mock.patch.object(su.shutil, "which", return_value=gh),
            mock.patch.object(su.subprocess, "run", return_value=done) as ran,
        ):
            path, how = su.verified_wheel(RELEASE, Path(self.tmp.name))
        return path, how, got, ran

    def test_a_matching_wheel_installs_and_says_how_it_was_checked(self):
        path, how, got, _ = self.fetch(f"{hashlib.sha256(self.WHEEL).hexdigest()}  NAME\n")
        self.assertEqual(path.read_bytes(), self.WHEEL)
        self.assertIn("matches the release's SHA256SUMS", how)
        self.assertIn("with `gh` on PATH", how)
        urls = [c.args[0] for c in got.call_args_list]
        self.assertTrue(all(u.startswith("https://github.com/thaithienvanid/aidd/releases/download/v1.1.0/") for u in urls), urls)

    def test_a_wheel_that_does_not_match_or_is_not_listed_installs_nothing(self):
        for sums in ("0" * 64 + "  NAME\n", "", f"{hashlib.sha256(self.WHEEL).hexdigest()}  other.whl\n"):
            with self.subTest(sums=sums[:20]):
                path, how, _, _ = self.fetch(sums)
                self.assertIsNone(path)
                self.assertTrue("does not match" in how or "does not list" in how, how)

    def test_with_gh_its_provenance_must_verify_too(self):
        good = f"{hashlib.sha256(self.WHEEL).hexdigest()} *NAME\n"
        path, how, _, ran = self.fetch(good, gh="/bin/gh")
        self.assertIsNotNone(path)
        self.assertIn("`gh` verified its build provenance", how)
        self.assertEqual(ran.call_args.args[0][:3], ["/bin/gh", "attestation", "verify"])
        path, how, _, _ = self.fetch(good, gh="/bin/gh", gh_code=1)
        self.assertIsNone(path)
        self.assertIn("refused", how)

    def test_main_is_never_verified_as_a_release(self):
        self.assertIsNone(su.verified_wheel(su.Target("main", C, None))[0])


class NeutralDirTests(unittest.TestCase):
    """The current directory may be a repository someone else wrote: its git config or uv.toml must never steer the update."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.object(su.resources, "cache_home", return_value=Path(self.tmp.name) / "cache")
        p.start()
        self.addCleanup(p.stop)

    def test_the_check_runs_git_outside_the_current_directory(self):
        with mock.patch.object(su.git, "run", return_value=f"{C}\trefs/tags/v1.1.0\n{A}\trefs/heads/main\n") as run:
            self.assertEqual(su.check(), su.Target("v1.1.0", C, "1.1.0"))
        where = Path(run.call_args.args[1])
        self.assertEqual(where, su.neutral_dir())
        self.assertNotEqual(where.resolve(), Path.cwd().resolve())
        self.assertEqual(run.call_args.kwargs["env"]["GIT_CEILING_DIRECTORIES"], str(where.parent))

    def test_the_reinstall_runs_outside_the_current_directory(self):
        with mock.patch.object(su.subprocess, "run", return_value=mock.Mock(returncode=0, stdout="", stderr="")) as run:
            su.run_update(["uv", "tool", "install"], quiet=True)
        self.assertEqual(Path(run.call_args.kwargs["cwd"]), su.neutral_dir())

    def test_a_repository_that_redirects_the_release_url_is_not_read(self):
        if not shutil.which("git"):
            self.skipTest("git is required")
        repo = Path(self.tmp.name) / "theirs"
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", f"url.{repo}/nowhere.insteadOf", su.RELEASE_REPO_URL], check=True)
        before = Path.cwd()
        os.chdir(repo)
        self.addCleanup(os.chdir, before)
        with mock.patch.object(su.git, "run", wraps=su.git.run) as run, mock.patch.dict(os.environ, {"GIT_TERMINAL_PROMPT": "0"}):
            su.check(timeout_seconds=1)
        self.assertNotEqual(Path(run.call_args.args[1]).resolve(), repo.resolve())


class SelfUpdateCommandTests(unittest.TestCase):
    def test_a_checkout_follows_itself(self):
        code, lines = su.self_update()
        self.assertEqual(code, 0)
        self.assertIn("git pull", lines[0])

    def test_check_only_changes_nothing(self):
        with (
            mock.patch.object(su, "install_kind", return_value="uv"),
            mock.patch.object(su, "check", return_value=su.Target("v2.0.0", C, "2.0.0")),
            mock.patch.object(su, "installed_commit", return_value=A),
            mock.patch.object(su.shutil, "which", return_value="/bin/uv"),
            mock.patch.object(su, "run_update") as run,
            mock.patch.dict(os.environ, {"AIDD_OFFLINE": ""}),
        ):
            code, lines = su.self_update(check_only=True)
        run.assert_not_called()
        self.assertEqual(code, 0)
        self.assertIn("would update", lines[0])
        self.assertIn(f"v2.0.0 ({C[:12]})", lines[0])
        self.assertIn("SHA256SUMS", lines[0])

    def test_with_no_release_it_names_the_main_opt_in(self):
        with (
            mock.patch.object(su, "install_kind", return_value="uv"),
            mock.patch.object(su, "check", return_value=None),
            mock.patch.dict(os.environ, {"AIDD_OFFLINE": ""}),
        ):
            code, lines = su.self_update()
        self.assertEqual(code, 2)
        self.assertIn("`aidd self-update --main`", lines[0])

    def test_unreachable_is_an_error(self):
        with (
            mock.patch.object(su, "install_kind", return_value="uv"),
            mock.patch.object(su, "check", return_value=None),
            mock.patch.dict(os.environ, {"AIDD_OFFLINE": ""}),
        ):
            code, _ = su.self_update()
        self.assertEqual(code, 2)

    def test_the_cli_runs_the_daily_check_after_every_command_with_its_name(self):
        with mock.patch.object(su, "auto_allowed", return_value=False) as allowed, redirect_stderr(io.StringIO()):
            app.main(["self-update", "--check"])
        allowed.assert_called_once_with("self-update")


if __name__ == "__main__":
    unittest.main()
