"""`aidd upgrade`: bring what aidd wrote into a repository up to this aidd, and nothing else."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT  # noqa: F401

from aidd import __version__
from aidd.setup import doctor_checks
from aidd.setup import antigravity_wiring, hook_wiring, upgrading
from aidd.setup import adoption
from aidd.setup import pins
from aidd.platforms import github_person


@unittest.skipUnless(shutil.which("git"), "git is required")
class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        adoption.init(
            self.root, adoption.InitOptions(profile="team", ci="github", links=[], approvers=["@lead"], team=True, harnesses=["claude-code"], ref="v1.0.0")
        )

    def tearDown(self):
        self.tmp.cleanup()

    def age(self):
        """What an older aidd left behind, plus the user's own edits, which an upgrade must keep."""
        wf = self.root / ".github" / "workflows" / "aidd-tests.yml"
        text = wf.read_text(encoding="utf-8").replace("@v1.0.0", "@v0.9.0")
        wf.write_text(text.replace("steps:\n", "steps:\n      - run: echo my own toolchain step\n", 1), encoding="utf-8")
        cfg = self.root / ".aidd" / "config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8").replace(f'aidd_version: "{__version__}"', 'aidd_version: "0.9.0"') + "\ngoal: kept\n", encoding="utf-8")
        (self.root / ".claude" / "commands" / "aidd-onboard.md").unlink()  # a command a later release added
        (self.root / ".agents" / "skills" / "aidd" / "SKILL.md").write_text("old skill\n", encoding="utf-8")
        (self.root / ".claude" / "agents" / "aidd-retired-role.md").write_text("gone\n", encoding="utf-8")
        return wf, cfg

    def test_a_dry_run_lists_every_change_and_makes_none(self):
        wf, _ = self.age()
        lines = upgrading.upgrade(self.root, ref="v1.0.0")
        text = "\n".join(lines)
        for expected in ("would update", "aidd-tests.yml", "would add", "aidd-onboard.md", "the skill", f"aidd_version {__version__}", "no longer shipped"):
            self.assertIn(expected, text, expected)
        self.assertIn("@v0.9.0", wf.read_text(encoding="utf-8"))

    def test_the_upgrade_keeps_what_you_changed(self):
        wf, cfg = self.age()
        upgrading.upgrade(self.root, ref="v1.0.0", yes=True)
        self.assertNotIn("@v0.9.0", wf.read_text(encoding="utf-8"))
        self.assertIn("my own toolchain step", wf.read_text(encoding="utf-8"))  # your steps stay
        self.assertIn(f'aidd_version: "{__version__}"', cfg.read_text(encoding="utf-8"))
        self.assertIn("goal: kept", cfg.read_text(encoding="utf-8"))  # your config stays
        self.assertTrue((self.root / ".claude" / "commands" / "aidd-onboard.md").is_file())
        self.assertNotEqual((self.root / ".agents" / "skills" / "aidd" / "SKILL.md").read_text(encoding="utf-8"), "old skill\n")
        self.assertTrue((self.root / ".claude" / "agents" / "aidd-retired-role.md").is_file())  # reported, never deleted
        again = upgrading.upgrade(self.root, ref="v1.0.0")
        self.assertEqual(
            [x for x in again if not x.startswith("no longer shipped")], [f"nothing to update: this repository already matches aidd {__version__}"]
        )

    def test_a_drifted_skill_and_a_stale_copy_point_at_aidd_upgrade_never_at_init_force(self):
        # `aidd init --force` also overwrites the config, so no drift hint may name it.
        (self.root / ".agents" / "skills" / "aidd" / "SKILL.md").write_text("old skill\n", encoding="utf-8")
        link = self.root / ".claude" / "skills" / "aidd"
        link.unlink()
        shutil.copytree(self.root / ".agents" / "skills" / "aidd", link)  # a copy, where symlinks are unavailable
        (link / "SKILL.md").write_text("older skill\n", encoding="utf-8")
        hints = [m for _, m in doctor_checks.doctor(self.root) if "skill differs" in m or "stale copy" in m]
        self.assertEqual(len(hints), 2, hints)
        for m in hints:
            self.assertIn("`aidd upgrade --yes`", m)
            self.assertNotIn("init --force", m)
        kept = [
            x
            for x in adoption.init(self.root, adoption.InitOptions(profile="team", ci="none", links=[], approvers=["@lead"], harnesses=[]))
            if "skills/aidd" in x
        ]
        self.assertTrue(kept and all("init --force" not in x and "--force upgrades" not in x for x in kept), kept)
        self.assertIn("`aidd upgrade --yes` upgrades it", "\n".join(kept))
        self.assertIn(".claude/skills/aidd", "\n".join(upgrading.upgrade(self.root, ref="v1.0.0")))  # the hint holds: upgrade refreshes the copy
        upgrading.upgrade(self.root, ref="v1.0.0", yes=True)
        checks = [m for _, m in doctor_checks.doctor(self.root)]
        self.assertIn(f"skill matches aidd {__version__}", checks)
        self.assertIn(".claude/skills/aidd is a copy that matches", checks)

    def test_a_commit_pin_keeps_the_release_as_a_comment(self):
        # Intentionally changed: the comment names a release only when the commit is known to be that release's.
        sha = "a" * 40
        self.assertEqual(pins.repin("uses: thaithienvanid/aidd@v0.9.0", sha, __version__), f"uses: thaithienvanid/aidd@{sha} # v{__version__}")
        # A commit nobody says is a release is labelled by its short SHA, never by the old release's tag.
        self.assertEqual(pins.repin("uses: thaithienvanid/aidd@v0.9.0 # v0.9.0", sha), f"uses: thaithienvanid/aidd@{sha} # aidd {sha[:12]}")
        self.assertEqual(pins.repin(f"uses: thaithienvanid/aidd@{'f' * 40} # aidd {'f' * 12}", sha), f"uses: thaithienvanid/aidd@{sha} # aidd {sha[:12]}")

    def test_repinning_a_gitlab_file_keeps_its_shell_string_intact(self):
        sha = "b" * 40
        text = (ROOT / "templates" / "gitlab" / "aidd.gitlab-ci.yml").read_text(encoding="utf-8")
        for release in (None, __version__):
            out = pins.repin(text, sha, release)
            self.assertIn(f'aidd_pin="thaithienvanid/aidd@{sha}"', out)
            self.assertNotIn(" # v", out.split("aidd_pin=", 1)[1].split("\n", 1)[0])

    def test_the_aidd_source_checkout_form_is_pinned_too(self):
        text = (ROOT / "templates" / "github" / "aidd-observe.yml").read_text(encoding="utf-8")
        self.assertRegex(text, r"repository: thaithienvanid/aidd\n\s+ref: v\d+\.\d+\.\d+")
        sha = "c" * 40
        self.assertIn(f"ref: {sha} # aidd {sha[:12]}\n", pins.pin_workflow(text, sha))
        self.assertIn(f"ref: {sha} # v{__version__}", pins.pin_workflow(text, sha, __version__))
        self.assertIn("ref: v9.9.9\n", pins.pin_workflow(text, "v9.9.9"))
        self.assertIn(f"ref: {sha} # v{__version__}", pins.repin(text, sha, __version__))
        self.assertIn(f"ref: {sha} # aidd {sha[:12]}\n", pins.repin(pins.pin_workflow(text, "d" * 40), sha))
        self.assertEqual(pins.unpinned(pins.pin_workflow(text, sha)), pins.unpinned(text))

    def test_an_installed_aidd_pins_ci_to_the_release_commit(self):
        sha = "e" * 40
        with tempfile.TemporaryDirectory() as d, mock.patch.object(pins, "installed_ref", return_value=None):
            root = Path(d)
            with mock.patch.object(pins, "release_commit", return_value=sha):
                lines = adoption.init(
                    root, adoption.InitOptions(profile="team", ci="github", links=[], skill=False, force=False, approvers=["@a"], harnesses=[])
                )
            self.assertIn(f"pinned   the aidd workflows to {sha} (the commit of release v{__version__})", lines)
            self.assertIn(
                f"thaithienvanid/aidd/.github/workflows/gate.yml@{sha} # v{__version__}",
                (root / ".github" / "workflows" / "aidd-gate.yml").read_text(encoding="utf-8"),
            )
        with tempfile.TemporaryDirectory() as d, mock.patch.object(pins, "installed_ref", return_value=None):
            root = Path(d)
            with mock.patch.object(pins, "release_commit", return_value=None):  # offline: keep the tag and say how to pin
                lines = adoption.init(
                    root, adoption.InitOptions(profile="team", ci="github", links=[], skill=False, force=False, approvers=["@a"], harnesses=[])
                )
            self.assertTrue(any("pin the aidd workflows to a commit SHA" in x for x in lines))
            self.assertIn(
                f"thaithienvanid/aidd/.github/workflows/gate.yml@v{__version__}", (root / ".github" / "workflows" / "aidd-gate.yml").read_text(encoding="utf-8")
            )

    def test_the_release_resolver_reads_ls_remote_and_never_fails(self):
        sha, tag_sha = "f" * 40, "1" * 40
        out = f"{tag_sha}\trefs/tags/v{__version__}\n{sha}\trefs/tags/v{__version__}^{{}}\n"
        with mock.patch.dict(os.environ, {"AIDD_OFFLINE": ""}):
            with mock.patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 0, out, "")) as run:
                self.assertEqual(pins.release_commit(), sha)  # the annotated tag peeled to its commit
                self.assertIn("ls-remote", run.call_args[0][0])
            with mock.patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("git", 5)):
                self.assertIsNone(pins.release_commit())
            with mock.patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 128, "", "offline")):
                self.assertIsNone(pins.release_commit())
        with mock.patch.dict(os.environ, {"AIDD_OFFLINE": "1"}), mock.patch.object(subprocess, "run") as run:
            self.assertIsNone(pins.release_commit())
            run.assert_not_called()


class PinLabelTests(unittest.TestCase):
    """A commit pin says `# v1.0.0` only when it is that release's commit; otherwise `# aidd <short sha>`."""

    def test_the_label_names_a_release_only_when_the_commit_is_one(self):
        sha = "1" * 40
        self.assertEqual(pins.pin_label(sha), f" # aidd {sha[:12]}")
        self.assertEqual(pins.pin_label(sha, "1.0.0"), " # v1.0.0")
        self.assertEqual(pins.pin_label("v1.0.0"), "")
        with mock.patch.object(pins, "release_tag_of", return_value="v1.0.0"):
            self.assertEqual(pins.pin_label(sha), " # v1.0.0")  # HEAD of the checkout is exactly the tag
            self.assertIn(f"@{sha} # v1.0.0", pins.pin_workflow("uses: thaithienvanid/aidd@v1.0.0\n", sha))


@unittest.skipUnless(shutil.which("git"), "git is required")
class PinExistsTests(unittest.TestCase):
    """`aidd doctor` checks, best effort, that the pinned aidd ref exists on GitHub."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.sha = "2" * 40
        adoption.init(self.root, adoption.InitOptions(profile="team", ci="github", links=[], approvers=["@lead"], harnesses=[], ref=self.sha))

    def tearDown(self):
        self.tmp.cleanup()

    def checks(self, refs):
        with mock.patch.dict(os.environ, {"AIDD_OFFLINE": "0"}), mock.patch.object(pins, "remote_refs", return_value=refs) as remote:
            return pins.pin_checks(self.root), remote

    def test_the_pinned_refs_are_read_from_the_ci_files(self):
        self.assertEqual(pins.pinned_refs(self.root), [self.sha])

    def test_skipped_without_a_github_remote_or_offline(self):
        out, remote = self.checks({})
        self.assertEqual(out, [])
        remote.assert_not_called()
        subprocess.run(["git", "remote", "add", "origin", "https://github.com/acme/app.git"], cwd=self.root, check=True)
        with mock.patch.object(pins, "remote_refs") as remote:
            self.assertEqual(pins.pin_checks(self.root), [])  # the suite runs with AIDD_OFFLINE=1
            remote.assert_not_called()

    def test_skipped_inside_a_hook(self):
        subprocess.run(["git", "remote", "add", "origin", "https://github.com/acme/app.git"], cwd=self.root, check=True)
        with mock.patch.dict(os.environ, {"AIDD_OFFLINE": "0", "AIDD_HOOK_OFFLINE": "1"}), mock.patch.object(pins, "remote_refs") as remote:
            self.assertEqual(pins.pin_checks(self.root), [])
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
        # The doctor's other network check, the branch rules on GitHub's API, is not under test: no request leaves.

        with (
            mock.patch.dict(os.environ, {"AIDD_OFFLINE": "0"}),
            mock.patch.object(pins, "remote_refs", return_value={}),
            mock.patch.object(github_person, "protection_checks", return_value=[]),
        ):
            self.assertIn("warn", [lvl for lvl, _ in doctor_checks.doctor(self.root)])


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(shutil.which("git") and os.name != "nt", "git, and the sh hook commands of a POSIX machine")
class GuardRefreshTests(unittest.TestCase):
    """`aidd upgrade` rewrites the guard aidd wired into Antigravity's hook file and Claude Code's repository hooks, as it
    does Codex's and Grok Build's: only aidd's own entries, never a person's hooks or settings."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def test_antigravity_hooks_from_an_older_aidd_are_rewritten_and_another_hook_stays(self):
        path = self.root / antigravity_wiring.HOOKS_FILE
        path.parent.mkdir(parents=True)
        old = {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "aidd hook pre-tool", "timeout": 20}]}]}
        mine = {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "./my-check"}]}]}
        path.write_text(json.dumps({antigravity_wiring.HOOK_NAME: old, "mine": mine}), encoding="utf-8")
        dry = upgrading.upgrade(self.root, ref="v1.0.0")
        self.assertTrue(any(a.startswith("would update") and ".agents/hooks.json" in a and "Antigravity" in a for a in dry), dry)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))[antigravity_wiring.HOOK_NAME], old)  # a dry run changes nothing
        upgrading.upgrade(self.root, ref="v1.0.0", yes=True)
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data[antigravity_wiring.HOOK_NAME], antigravity_wiring.hook_spec())
        self.assertEqual(data["mine"], mine)
        self.assertFalse(any(".agents/hooks.json" in a for a in upgrading.upgrade(self.root, ref="v1.0.0")))

    def test_claude_code_hooks_aidd_wrote_are_rewritten_and_the_persons_settings_stay(self):
        settings = self.root / ".claude" / "settings.json"
        settings.parent.mkdir()
        theirs = {"matcher": "Bash", "hooks": [{"type": "command", "command": "./my-check"}]}
        data = {
            "model": "opus",
            "permissions": {"allow": ["Bash(make *)"]},
            "hooks": {
                "PreToolUse": [{"matcher": "Edit|Write", "hooks": [{"type": "command", "command": "aidd hook pre-tool", "timeout": 20}]}, theirs],
                "Stop": [{"hooks": [{"type": "command", "command": "aidd hook stop", "timeout": 10}]}],
            },
        }
        settings.write_text(json.dumps(data), encoding="utf-8")
        dry = upgrading.upgrade(self.root, ref="v1.0.0")
        self.assertTrue(any(a.startswith("would update") and ".claude/settings.json" in a and "PreToolUse, Stop" in a for a in dry), dry)
        self.assertEqual(json.loads(settings.read_text(encoding="utf-8")), data)
        upgrading.upgrade(self.root, ref="v1.0.0", yes=True)
        after = json.loads(settings.read_text(encoding="utf-8"))
        guard = after["hooks"]["PreToolUse"][0]
        self.assertEqual(guard["matcher"], hook_wiring.HOOK_MATCHER)
        self.assertEqual(guard["hooks"][0]["command"], hook_wiring.hook_command("pre-tool"))
        self.assertEqual(after["hooks"]["Stop"][0]["hooks"][0]["command"], hook_wiring.hook_command("stop"))
        self.assertEqual(after["hooks"]["PreToolUse"][1], theirs)
        self.assertEqual((after["model"], after["permissions"]), (data["model"], data["permissions"]))
        self.assertNotIn("SessionStart", after["hooks"])  # it rewrites aidd's hooks, and adds none the person removed
        self.assertFalse(any(".claude/settings.json" in a for a in upgrading.upgrade(self.root, ref="v1.0.0")))

    def test_a_command_with_a_persons_step_or_environment_stays_as_they_wrote_it(self):
        settings = self.root / ".claude" / "settings.json"
        settings.parent.mkdir()
        theirs = ["./scripts/notify.sh && aidd hook stop || true", "AIDD_SPEC=SPEC-9 ~/.local/bin/aidd hook stop", "aidd hook stop --x || true"]
        data = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": c} for c in theirs]}]}}
        settings.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(hook_wiring.refresh_claude_hooks(self.root, write=True), ([], [f"Stop runs `{c}`" for c in theirs]))
        actions = upgrading.upgrade(self.root, ref="v1.0.0", yes=True)
        self.assertEqual(json.loads(settings.read_text(encoding="utf-8")), data)
        notes = [a for a in actions if ".claude/settings.json" in a]
        self.assertEqual(len(notes), 3, notes)
        for note, command in zip(notes, theirs, strict=True):
            self.assertTrue(note.startswith("kept     ") and ".claude/settings.json (left as you wrote it: Stop runs `" in note, note)
            self.assertIn(command, note)
            self.assertIn("aidd init --claude-hooks", note)  # the next step

    def test_aidds_own_older_forms_are_rewritten(self):
        settings = self.root / ".claude" / "settings.json"
        settings.parent.mkdir()
        machine = hook_wiring._shell_launcher(["/usr/bin/python3", "-I", "-m", "aidd"], {})
        olds = {"Stop": "aidd hook stop || true", "SubagentStop": "aidd hook stop", "SessionStart": f"{machine} hook session-start || true"}
        settings.write_text(json.dumps({"hooks": {e: [{"hooks": [{"type": "command", "command": c}]}] for e, c in olds.items()}}), encoding="utf-8")
        self.assertEqual(sorted(hook_wiring.refresh_claude_hooks(self.root, write=True)[0]), sorted(olds))
        after = json.loads(settings.read_text(encoding="utf-8"))["hooks"]
        for event, sub in (("Stop", "stop"), ("SubagentStop", "stop"), ("SessionStart", "session-start")):
            self.assertEqual(after[event][0]["hooks"][0]["command"], hook_wiring.hook_command(sub))
        self.assertEqual(hook_wiring.refresh_claude_hooks(self.root, write=False), ([], []))

    def test_a_group_shared_with_a_persons_hook_keeps_its_matcher(self):
        # Widening the group would run the person's lint on every Bash and MCP call: aidd's hook moves to a group of its own.
        settings = self.root / ".claude" / "settings.json"
        settings.parent.mkdir()
        lint = {"type": "command", "command": "./scripts/lint-on-edit.sh"}
        guard = {"type": "command", "command": "aidd hook pre-tool", "timeout": 20}
        settings.write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Edit|Write", "hooks": [lint, guard]}]}}), encoding="utf-8")
        self.assertEqual(hook_wiring.refresh_claude_hooks(self.root, write=True), (["PreToolUse"], []))
        groups = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
        self.assertEqual(groups[0], {"matcher": "Edit|Write", "hooks": [lint]})
        self.assertEqual(groups[1], {"matcher": hook_wiring.HOOK_MATCHER, "hooks": [{**guard, "command": hook_wiring.hook_command("pre-tool")}]})
        self.assertEqual(hook_wiring.refresh_claude_hooks(self.root, write=False), ([], []))

    def test_the_file_keeps_its_indentation_and_its_text_as_written(self):
        settings = self.root / ".claude" / "settings.json"
        settings.parent.mkdir()
        data = {"env": {"NAME": "Café ✓"}, "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "aidd hook stop || true"}]}]}}
        want = json.loads(json.dumps(data))
        want["hooks"]["Stop"][0]["hooks"][0]["command"] = hook_wiring.hook_command("stop")
        for indent, newline in ((4, "\n"), ("\t", "\n"), (None, "")):
            with self.subTest(indent=indent):
                settings.write_text(json.dumps(data, indent=indent, ensure_ascii=False) + newline, encoding="utf-8")
                hook_wiring.refresh_claude_hooks(self.root, write=True)
                self.assertEqual(settings.read_text(encoding="utf-8"), json.dumps(want, indent=indent, ensure_ascii=False) + newline)

    def test_settings_with_no_aidd_hook_or_not_json_are_left_alone(self):
        settings = self.root / ".claude" / "settings.json"
        settings.parent.mkdir()
        for text in (json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "./x"}]}]}}), "{not json"):
            with self.subTest(text[:10]):
                settings.write_text(text, encoding="utf-8")
                self.assertEqual(hook_wiring.refresh_claude_hooks(self.root, write=False), ([], []))
                self.assertFalse(any(".claude/settings.json" in a for a in upgrading.upgrade(self.root, ref="v1.0.0", yes=True)))
                self.assertEqual(settings.read_text(encoding="utf-8"), text)
