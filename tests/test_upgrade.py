"""`aidd upgrade`: bring what aidd wrote into a repository up to this aidd, and nothing else."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT  # noqa: F401

from aidd import __version__, repo


@unittest.skipUnless(shutil.which("git"), "git is required")
class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        repo.init(self.root, profile="team", ci="github", links=[], approvers=["@lead"], team=True, harnesses=["claude-code"], ref="v1.0.0")

    def tearDown(self):
        self.tmp.cleanup()

    def age(self):
        """What an older aidd left behind, plus the user's own edits, which an upgrade must keep."""
        wf = self.root / ".github" / "workflows" / "aidd-tests.yml"
        text = wf.read_text(encoding="utf-8").replace("@v1.0.0", "@v0.9.0")
        wf.write_text(text.replace("steps:\n", "steps:\n      - run: echo my own toolchain step\n", 1), encoding="utf-8")
        cfg = self.root / ".aidd" / "config.toml"
        cfg.write_text(
            cfg.read_text(encoding="utf-8").replace(f'aidd_version = "{__version__}"', 'aidd_version = "0.9.0"') + '\ngoal = "kept"\n', encoding="utf-8"
        )
        (self.root / ".claude" / "commands" / "aidd-onboard.md").unlink()  # a command a later release added
        (self.root / ".agents" / "skills" / "aidd" / "SKILL.md").write_text("old skill\n", encoding="utf-8")
        (self.root / ".claude" / "agents" / "aidd-retired-role.md").write_text("gone\n", encoding="utf-8")
        return wf, cfg

    def test_a_dry_run_lists_every_change_and_makes_none(self):
        wf, _ = self.age()
        lines = repo.upgrade(self.root, ref="v1.0.0")
        text = "\n".join(lines)
        for expected in ("would update", "aidd-tests.yml", "would add", "aidd-onboard.md", "the skill", f"aidd_version {__version__}", "no longer shipped"):
            self.assertIn(expected, text, expected)
        self.assertIn("@v0.9.0", wf.read_text(encoding="utf-8"))

    def test_the_upgrade_keeps_what_you_changed(self):
        wf, cfg = self.age()
        repo.upgrade(self.root, ref="v1.0.0", yes=True)
        self.assertNotIn("@v0.9.0", wf.read_text(encoding="utf-8"))
        self.assertIn("my own toolchain step", wf.read_text(encoding="utf-8"))  # your steps stay
        self.assertIn(f'aidd_version = "{__version__}"', cfg.read_text(encoding="utf-8"))
        self.assertIn('goal = "kept"', cfg.read_text(encoding="utf-8"))  # your config stays
        self.assertTrue((self.root / ".claude" / "commands" / "aidd-onboard.md").is_file())
        self.assertNotEqual((self.root / ".agents" / "skills" / "aidd" / "SKILL.md").read_text(encoding="utf-8"), "old skill\n")
        self.assertTrue((self.root / ".claude" / "agents" / "aidd-retired-role.md").is_file())  # reported, never deleted
        again = repo.upgrade(self.root, ref="v1.0.0")
        self.assertEqual(
            [x for x in again if not x.startswith("no longer shipped")], [f"nothing to update: this repository already matches aidd {__version__}"]
        )

    def test_a_commit_pin_keeps_the_release_as_a_comment(self):
        # Intentionally changed: the comment names a release only when the commit is known to be that release's.
        sha = "a" * 40
        self.assertEqual(repo.repin("uses: thaithienvanid/aidd@v0.9.0", sha, __version__), f"uses: thaithienvanid/aidd@{sha} # v{__version__}")
        # A commit nobody says is a release is labelled by its short SHA, never by the old release's tag.
        self.assertEqual(repo.repin("uses: thaithienvanid/aidd@v0.9.0 # v0.9.0", sha), f"uses: thaithienvanid/aidd@{sha} # aidd {sha[:12]}")
        self.assertEqual(repo.repin(f"uses: thaithienvanid/aidd@{'f' * 40} # aidd {'f' * 12}", sha), f"uses: thaithienvanid/aidd@{sha} # aidd {sha[:12]}")

    def test_repinning_a_gitlab_file_keeps_its_shell_string_intact(self):
        sha = "b" * 40
        text = (ROOT / "templates" / "gitlab" / "aidd.gitlab-ci.yml").read_text(encoding="utf-8")
        for release in (None, __version__):
            out = repo.repin(text, sha, release)
            self.assertIn(f'aidd_pin="thaithienvanid/aidd@{sha}"', out)
            self.assertNotIn(" # v", out.split("aidd_pin=", 1)[1].split("\n", 1)[0])

    def test_the_aidd_source_checkout_form_is_pinned_too(self):
        text = (ROOT / "templates" / "github" / "aidd-watch.yml").read_text(encoding="utf-8")
        self.assertRegex(text, r"repository: thaithienvanid/aidd\n\s+ref: v\d+\.\d+\.\d+")
        sha = "c" * 40
        self.assertIn(f"ref: {sha} # aidd {sha[:12]}\n", repo.pin_workflow(text, sha))
        self.assertIn(f"ref: {sha} # v{__version__}", repo.pin_workflow(text, sha, __version__))
        self.assertIn("ref: v9.9.9\n", repo.pin_workflow(text, "v9.9.9"))
        self.assertIn(f"ref: {sha} # v{__version__}", repo.repin(text, sha, __version__))
        self.assertIn(f"ref: {sha} # aidd {sha[:12]}\n", repo.repin(repo.pin_workflow(text, "d" * 40), sha))
        self.assertEqual(repo.unpinned(repo.pin_workflow(text, sha)), repo.unpinned(text))

    def test_an_installed_aidd_pins_ci_to_the_release_commit(self):
        sha = "e" * 40
        with tempfile.TemporaryDirectory() as d, mock.patch.object(repo, "installed_ref", return_value=None):
            root = Path(d)
            with mock.patch.object(repo, "release_commit", return_value=sha):
                lines = repo.init(root, profile="team", ci="github", links=[], skill=False, force=False, approvers=["@a"], harnesses=[])
            self.assertIn(f"pinned   the aidd workflows to {sha} (the commit of release v{__version__})", lines)
            self.assertIn(
                f"thaithienvanid/aidd/.github/workflows/gate.yml@{sha} # v{__version__}",
                (root / ".github" / "workflows" / "aidd-gate.yml").read_text(encoding="utf-8"),
            )
        with tempfile.TemporaryDirectory() as d, mock.patch.object(repo, "installed_ref", return_value=None):
            root = Path(d)
            with mock.patch.object(repo, "release_commit", return_value=None):  # offline: keep the tag and say how to pin
                lines = repo.init(root, profile="team", ci="github", links=[], skill=False, force=False, approvers=["@a"], harnesses=[])
            self.assertTrue(any("pin the aidd workflows to a commit SHA" in x for x in lines))
            self.assertIn(
                f"thaithienvanid/aidd/.github/workflows/gate.yml@v{__version__}", (root / ".github" / "workflows" / "aidd-gate.yml").read_text(encoding="utf-8")
            )

    def test_the_release_resolver_reads_ls_remote_and_never_fails(self):
        sha, tag_sha = "f" * 40, "1" * 40
        out = f"{tag_sha}\trefs/tags/v{__version__}\n{sha}\trefs/tags/v{__version__}^{{}}\n"
        with mock.patch.dict(os.environ, {"AIDD_OFFLINE": ""}):
            with mock.patch.object(repo.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, out, "")) as run:
                self.assertEqual(repo.release_commit(), sha)  # the annotated tag peeled to its commit
                self.assertIn("ls-remote", run.call_args[0][0])
            with mock.patch.object(repo.subprocess, "run", side_effect=subprocess.TimeoutExpired("git", 5)):
                self.assertIsNone(repo.release_commit())
            with mock.patch.object(repo.subprocess, "run", return_value=subprocess.CompletedProcess([], 128, "", "offline")):
                self.assertIsNone(repo.release_commit())
        with mock.patch.dict(os.environ, {"AIDD_OFFLINE": "1"}), mock.patch.object(repo.subprocess, "run") as run:
            self.assertIsNone(repo.release_commit())
            run.assert_not_called()


class PinLabelTests(unittest.TestCase):
    """A commit pin says `# v1.0.0` only when it is that release's commit; otherwise `# aidd <short sha>`."""

    def test_the_label_names_a_release_only_when_the_commit_is_one(self):
        sha = "1" * 40
        self.assertEqual(repo.pin_label(sha), f" # aidd {sha[:12]}")
        self.assertEqual(repo.pin_label(sha, "1.0.0"), " # v1.0.0")
        self.assertEqual(repo.pin_label("v1.0.0"), "")
        with mock.patch.object(repo, "release_tag_of", return_value="v1.0.0"):
            self.assertEqual(repo.pin_label(sha), " # v1.0.0")  # HEAD of the checkout is exactly the tag
            self.assertIn(f"@{sha} # v1.0.0", repo.pin_workflow("uses: thaithienvanid/aidd@v1.0.0\n", sha))


@unittest.skipUnless(shutil.which("git"), "git is required")
class PinExistsTests(unittest.TestCase):
    """`aidd doctor` checks, best effort, that the pinned aidd ref exists on GitHub."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.sha = "2" * 40
        repo.init(self.root, profile="team", ci="github", links=[], approvers=["@lead"], harnesses=[], ref=self.sha)

    def tearDown(self):
        self.tmp.cleanup()

    def checks(self, refs):
        with mock.patch.dict(os.environ, {"AIDD_OFFLINE": "0"}), mock.patch.object(repo, "remote_refs", return_value=refs) as remote:
            return repo.pin_checks(self.root), remote

    def test_the_pinned_refs_are_read_from_the_ci_files(self):
        self.assertEqual(repo.pinned_refs(self.root), [self.sha])

    def test_skipped_without_a_github_remote_or_offline(self):
        out, remote = self.checks({})
        self.assertEqual(out, [])
        remote.assert_not_called()
        subprocess.run(["git", "remote", "add", "origin", "https://github.com/acme/app.git"], cwd=self.root, check=True)
        with mock.patch.object(repo, "remote_refs") as remote:
            self.assertEqual(repo.pin_checks(self.root), [])  # the suite runs with AIDD_OFFLINE=1
            remote.assert_not_called()

    def test_a_missing_pin_warns_and_a_present_one_is_ok(self):
        subprocess.run(["git", "remote", "add", "origin", "git@github.com:acme/app.git"], cwd=self.root, check=True)
        out, _ = self.checks({"refs/heads/main": "3" * 40})
        self.assertEqual([lvl for lvl, _ in out], ["warn"])
        self.assertIn("not the tip of any branch or tag", out[0][1])
        out, _ = self.checks({"refs/heads/main": self.sha})
        self.assertEqual([lvl for lvl, _ in out], ["ok"])
        out, _ = self.checks(None)
        self.assertEqual(out, [("ok", "the aidd pin was not checked: GitHub could not be reached")])
        with mock.patch.dict(os.environ, {"AIDD_OFFLINE": "0"}), mock.patch.object(repo, "remote_refs", return_value={}):
            self.assertIn("warn", [lvl for lvl, _ in repo.doctor(self.root)])


if __name__ == "__main__":
    unittest.main()
