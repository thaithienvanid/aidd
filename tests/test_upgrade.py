"""`aidd upgrade`: bring what aidd wrote into a repository up to this aidd, and nothing else."""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT, RepoTemplateCase

from aidd import __version__
from aidd.setup import doctor_checks
from aidd.setup import upgrading
from aidd.setup import adoption
from aidd.setup import pins


@unittest.skipUnless(shutil.which("git"), "git is required")
class UpgradeTests(RepoTemplateCase):
    @classmethod
    def build_template(cls, root: Path) -> None:
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        adoption.init(
            root, adoption.InitOptions(profile="team", ci="github", links=[], approvers=["@lead"], aidd_team=True, harnesses=["claude-code"], ref="v1.0.0")
        )

    def age(self):
        """What an older aidd left behind, plus the user's own edits, which an upgrade must keep."""
        wf = self.root / ".github" / "workflows" / "aidd-tests.yml"
        text = wf.read_text(encoding="utf-8").replace("@v1.0.0", "@v0.9.0")
        wf.write_text(text.replace("steps:\n", "steps:\n      - run: echo my own toolchain step\n", 1), encoding="utf-8")
        cfg = self.root / ".aidd" / "config.yaml"
        cfg.write_text(
            cfg.read_text(encoding="utf-8").replace(f'aidd_version: "{__version__}"', 'aidd_version: "0.9.0"') + "\nspecs_dir: kept\n", encoding="utf-8"
        )
        (self.root / ".claude" / "commands" / "aidd-onboard.md").unlink()  # a command a later release added
        (self.root / ".agents" / "skills" / "aidd" / "SKILL.md").write_text("old skill\n", encoding="utf-8")
        return wf, cfg

    def test_a_dry_run_lists_every_change_and_makes_none(self):
        wf, _ = self.age()
        lines = upgrading.upgrade(self.root, ref="v1.0.0")
        text = "\n".join(lines)
        for expected in ("would update", "aidd-tests.yml", "would add", "aidd-onboard.md", "the skill", f"aidd_version {__version__}"):
            self.assertIn(expected, text, expected)
        self.assertIn("@v0.9.0", wf.read_text(encoding="utf-8"))

    def test_the_upgrade_keeps_what_you_changed(self):
        wf, cfg = self.age()
        upgrading.upgrade(self.root, ref="v1.0.0", yes=True)
        self.assertNotIn("@v0.9.0", wf.read_text(encoding="utf-8"))
        self.assertIn("my own toolchain step", wf.read_text(encoding="utf-8"))  # your steps stay
        self.assertIn(f'aidd_version: "{__version__}"', cfg.read_text(encoding="utf-8"))
        self.assertIn("specs_dir: kept", cfg.read_text(encoding="utf-8"))  # your config stays
        self.assertTrue((self.root / ".claude" / "commands" / "aidd-onboard.md").is_file())
        self.assertNotEqual((self.root / ".agents" / "skills" / "aidd" / "SKILL.md").read_text(encoding="utf-8"), "old skill\n")
        again = upgrading.upgrade(self.root, ref="v1.0.0")
        self.assertEqual(again, [f"nothing to update: this repository already matches aidd {__version__}"])

    def stale_agents(self):
        """An AGENTS.md whose aidd sections name a removed command and a retired role (both closed by their end marks),
        with the person's own text above, below, and between them. Returns the person's lines."""
        agents = self.root / "AGENTS.md"
        text = agents.read_text(encoding="utf-8")
        text = text.replace("This repository uses aidd.", "Run `aidd gate` before every merge. This repository uses aidd.", 1)
        text = text.replace("| Role | Loop steps | Writes |", "| `aidd-retired-role` | x | y |\n| Role | Loop steps | Writes |", 1)
        mine = ["Our own rule: never touch billing.", "## Our deploy notes", "### Fridays", "Deploy on Fridays, never.", "After the team section."]
        body = text.split("# Agents", 1)[1].strip()
        body = body.replace("<!-- /aidd -->", f"<!-- /aidd -->\n\n{mine[1]}\n\n{mine[2]}\n\n{mine[3]}", 1)
        agents.write_text(f"# Agents\n\n{mine[0]}\n\n{body}\n\n{mine[4]}\n", encoding="utf-8")
        return mine

    def test_an_upgrade_refreshes_only_the_text_between_aidd_marks(self):
        mine = self.stale_agents()
        agents = self.root / "AGENTS.md"
        before = agents.read_text(encoding="utf-8")
        lines = upgrading.upgrade(self.root, ref="v1.0.0")
        self.assertTrue(any(x.startswith("would update") and "AGENTS.md" in x for x in lines), lines)
        self.assertEqual(agents.read_text(encoding="utf-8"), before, "a dry run writes nothing")
        upgrading.upgrade(self.root, ref="v1.0.0", yes=True)
        new = agents.read_text(encoding="utf-8")
        self.assertNotIn("aidd gate", new)
        self.assertNotIn("aidd-retired-role", new)
        for line in mine:
            self.assertIn(line, new, "a person's own text stays, a subsection and the text after the team section too")
        self.assertLess(new.index(mine[0]), new.index("<!-- aidd -->"), "the person's text above the marks stays above")
        self.assertEqual(new.count("<!-- /aidd -->"), 1)
        self.assertEqual(new.count("<!-- /aidd-team -->"), 1)
        again = upgrading.upgrade(self.root, ref="v1.0.0")
        self.assertEqual(again, [f"nothing to update: this repository already matches aidd {__version__}"])

    def unclosed(self, tail: str = "## Ours\n\nkeep me\n") -> tuple[Path, str]:
        """An AGENTS.md whose aidd section has an opening mark and no end mark. Returns the file and that section."""
        agents = self.root / "AGENTS.md"
        section = adoption.agents_snippet(self.root, True).replace("\n<!-- /aidd -->\n", "\n").rstrip("\n") + "\n"
        agents.write_text(f"# Agents\n\nmine above\n\n{section}\n{tail}", encoding="utf-8")
        return agents, section

    def test_a_section_with_no_end_mark_is_reported_and_left_alone(self):
        for edit in ("", "Our own line.\n", "### Our subsection\n\ntext\n"):
            with self.subTest(edit=edit):
                agents, _ = self.unclosed(edit + "## Ours\n\nkeep me\n")
                before = agents.read_text(encoding="utf-8")
                lines = upgrading.upgrade(self.root, ref="v1.0.0", yes=True)
                self.assertEqual(agents.read_text(encoding="utf-8"), before)
                (note,) = [x for x in lines if x.startswith("note     ") and "AGENTS.md" in x]
                self.assertIn("left alone", note)
                self.assertIn("delete that section and run `aidd init`", note)

    def test_the_note_for_a_section_left_alone_names_its_lines(self):
        agents, _ = self.unclosed()
        lines = agents.read_text(encoding="utf-8").splitlines()
        last = lines.index("## Ours") - 1  # the blank line before the next heading is not the section's
        (note,) = [x for x in upgrading.refreshed_instruction_files(self.root, "")[1] if "AGENTS.md" in x]
        self.assertIn(f"the section at <!-- aidd --> (lines 5 to {last})", note)

    def test_a_current_config_with_mixed_line_endings_is_not_rewritten(self):
        cfg = self.root / ".aidd" / "config.yaml"
        mixed = cfg.read_bytes().replace(b"\n", b"\r\n", 1)
        cfg.write_bytes(mixed)
        lines = upgrading.upgrade(self.root, ref="v1.0.0", yes=True)
        self.assertEqual(cfg.read_bytes(), mixed, "nothing changed, so the file is byte for byte as it was")
        self.assertEqual([x for x in lines if "config.yaml" in x], [])

    def test_the_note_for_a_section_left_alone_names_the_lines_of_the_file_as_it_will_read(self):
        agents = self.root / "AGENTS.md"
        text = agents.read_text(encoding="utf-8").replace("<!-- /aidd-team -->", "Our own line.", 1)  # the team section: no end mark, edited
        text = text.replace("This repository uses aidd.", "This repository uses aidd.\n\nextra one\n\nextra two\n\nextra three", 1)  # the aidd section shrinks
        agents.write_text(text, encoding="utf-8")

        def team_note(lines):
            (note,) = [x for x in lines if "aidd-team -->" in x and x.startswith("note     ")]
            return int(re.search(r"\(lines? (\d+)", note).group(1))

        before = agents.read_text(encoding="utf-8").splitlines().index("<!-- aidd-team -->") + 1
        self.assertEqual(team_note(upgrading.upgrade(self.root, ref="v1.0.0")), before, "a dry run names the lines as they are now")
        lines = upgrading.upgrade(self.root, ref="v1.0.0", yes=True)
        after = agents.read_text(encoding="utf-8").splitlines().index("<!-- aidd-team -->") + 1
        self.assertLess(after, before)
        self.assertEqual(team_note(lines), after, "--yes names the lines of the file it wrote")

    def test_a_mark_in_a_code_fence_is_no_mark(self):
        fenced = "# Agents\n\nSample:\n\n```md\n<!-- aidd -->\n## Change control\n\nrun `aidd gate`\n```\n\nEnd.\n"
        agents = self.root / "AGENTS.md"
        agents.write_text(fenced, encoding="utf-8")
        self.assertEqual(upgrading.refreshed_instruction_files(self.root, "")[0], {})

    def test_the_file_keeps_its_line_endings(self):
        self.stale_agents()
        agents = self.root / "AGENTS.md"
        raw = agents.read_bytes().replace(b"\n", b"\r\n")
        agents.write_bytes(raw)
        upgrading.upgrade(self.root, ref="v1.0.0", yes=True)
        new = agents.read_bytes()
        self.assertNotIn(b"aidd gate", new)
        self.assertEqual(new.count(b"\r\n"), new.count(b"\n"), "every line ending is still CRLF")

    def test_the_team_section_is_refreshed_when_the_plugin_carries_the_team_and_no_file_of_ours_is_installed(self):
        agents = self.root / "AGENTS.md"
        for rel in [p for p in self.root.rglob("aidd-*") if p.is_file() and ".claude" in p.parts]:
            rel.unlink()
        text = agents.read_text(encoding="utf-8").replace(
            "| Role | Loop steps | Writes |", "| `aidd-retired-role` | x | y |\n| Role | Loop steps | Writes |", 1
        )
        agents.write_text(text, encoding="utf-8")
        upgrading.upgrade(self.root, ref="v1.0.0", yes=True)
        self.assertNotIn("aidd-retired-role", agents.read_text(encoding="utf-8"))

    def test_an_older_aidd_writes_nothing_over_a_newer_one(self):
        """An upgrade writes the files of the aidd that runs it, so one older than the config's writes nothing."""
        cfg = self.root / ".aidd" / "config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8").replace(f'aidd_version: "{__version__}"', 'aidd_version: "99.0.0"'), encoding="utf-8")
        skill = self.root / ".agents" / "skills" / "aidd" / "SKILL.md"
        skill.write_text("a newer skill\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, r"names aidd 99\.0\.0, newer than this aidd .*run `aidd self-update` first"):
            upgrading.upgrade(self.root, ref="v1.0.0", yes=True)
        self.assertEqual(skill.read_text(encoding="utf-8"), "a newer skill\n")

    def test_aidd_own_source_is_upgraded_only_by_its_own_code(self):
        """In aidd's own source the skill and the templates are the source, so an installed aidd, perhaps an older
        one, never writes over them (`/aidd update` once put an older skill line back)."""
        (self.root / "schemas").mkdir()
        (self.root / "src" / "aidd").mkdir(parents=True)
        (self.root / "pyproject.toml").write_text('[project]\nname = "aidd"\n', encoding="utf-8")
        skill = self.root / ".agents" / "skills" / "aidd" / "SKILL.md"
        skill.write_text("the source\n", encoding="utf-8")
        with mock.patch("aidd.kernel.resources.repo_root", return_value=None):
            with self.assertRaisesRegex(ValueError, r"is aidd's own source.*`PYTHONPATH=src python3 -m aidd upgrade --yes` there"):
                upgrading.upgrade(self.root, ref="v1.0.0", yes=True)
        self.assertEqual(skill.read_text(encoding="utf-8"), "the source\n")
        with mock.patch("aidd.kernel.resources.repo_root", return_value=self.root):
            self.assertIsNone(upgrading.older_than_repository(self.root))  # its own checkout upgrades it
        (self.root / "pyproject.toml").write_text('[project]\nname = "billing"\n', encoding="utf-8")
        with mock.patch("aidd.kernel.resources.repo_root", return_value=None):
            self.assertIsNone(upgrading.older_than_repository(self.root))  # a project that only looks like aidd's source

    def test_a_config_version_aidd_cannot_read_writes_nothing(self):
        cfg = self.root / ".aidd" / "config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8").replace(f'aidd_version: "{__version__}"', "aidd_version: main"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, r"names aidd_version 'main', which is no version: write it as"):
            upgrading.upgrade(self.root, ref="v1.0.0", yes=True)

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

    def test_an_installed_aidd_pins_ci_to_the_release_commit(self):
        sha = "e" * 40
        with tempfile.TemporaryDirectory() as d, mock.patch.object(pins, "installed_ref", return_value=None):
            root = Path(d)
            with mock.patch.object(pins, "release_commit", return_value=sha):
                lines = adoption.init(
                    root, adoption.InitOptions(profile="team", ci="github", links=[], skill=False, force=False, approvers=["@a"], harnesses=[])
                )
            self.assertIn(f"pinned   the aidd workflow to {sha} (the commit of release v{__version__})", lines)
            self.assertIn(
                f"thaithienvanid/aidd@{sha} # v{__version__}",
                (root / ".github" / "workflows" / "aidd-tests.yml").read_text(encoding="utf-8"),
            )
        with tempfile.TemporaryDirectory() as d, mock.patch.object(pins, "installed_ref", return_value=None):
            root = Path(d)
            with mock.patch.object(pins, "release_commit", return_value=None):  # offline: keep the tag and say how to pin
                lines = adoption.init(
                    root, adoption.InitOptions(profile="team", ci="github", links=[], skill=False, force=False, approvers=["@a"], harnesses=[])
                )
            self.assertTrue(any("pin the aidd workflow to a commit SHA" in x for x in lines))
            self.assertIn(f"thaithienvanid/aidd@v{__version__}", (root / ".github" / "workflows" / "aidd-tests.yml").read_text(encoding="utf-8"))

    def test_upgrade_writes_nothing_through_a_link(self):
        """A CI file the repository links to a file outside it keeps its pin: upgrade says so, and writes nothing there."""
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as away:
            root, target = Path(d), Path(away) / "aidd-tests.yml"
            adoption.init(root, adoption.InitOptions(profile="team", ci="none", links=[], skill=False, force=False, approvers=["@a"], harnesses=[]))
            target.write_text(f"jobs:\n  t:\n    uses: thaithienvanid/aidd@v{__version__}\n", encoding="utf-8")
            before = target.read_text(encoding="utf-8")
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "aidd-tests.yml").symlink_to(target)
            lines = upgrading.upgrade(root, ref="c" * 40, yes=True)
            self.assertEqual(target.read_text(encoding="utf-8"), before)
            self.assertTrue(any(x.startswith("skipped  ") and "(.github/workflows/aidd-tests.yml is a link" in x for x in lines), lines)
            self.assertNotIn("nothing to update", lines[0])

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
class PinExistsTests(RepoTemplateCase):
    """`aidd doctor` checks, best effort, that the pinned aidd ref exists on GitHub."""

    sha = "2" * 40

    @classmethod
    def build_template(cls, root: Path) -> None:
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        adoption.init(root, adoption.InitOptions(profile="team", ci="github", links=[], approvers=["@lead"], harnesses=[], ref=cls.sha))

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

    def test_skipped_offline(self):
        subprocess.run(["git", "remote", "add", "origin", "https://github.com/acme/app.git"], cwd=self.root, check=True)
        with mock.patch.dict(os.environ, {"AIDD_OFFLINE": "1"}), mock.patch.object(pins, "remote_refs") as remote:
            self.assertEqual(pins.pin_checks(self.root), [])
            remote.assert_not_called()


if __name__ == "__main__":
    unittest.main()
