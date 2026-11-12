"""`aidd init --dry-run`. The dry run is the real init run inside a plan, so it names the files and prints the config the
real run writes, for every flag."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import aidd_here, delegation_moment_pinned, src_pythonpath
from init_plan_helpers import FLAGS, files_of, folders_of, plan_of, repo

from aidd import setup
from aidd.cli import parser
from aidd.kernel import regular_files
from aidd.setup import mcp_wiring


class DryRunIsTheRealRunTests(unittest.TestCase):
    def test_the_cases_set_every_flag_init_has(self):
        """A flag added to `init` joins FLAGS, so the dry run is held to the real run for it too."""
        init = parser.build_parser()._subparsers._group_actions[0].choices["init"]  # type: ignore[union-attr]
        flags = {o for a in init._actions for o in a.option_strings if o.startswith("--")} - {"--help", "--dry-run", "--force"}
        self.assertEqual(sorted(flags - {x for case in FLAGS for x in case}), [])

    @delegation_moment_pinned()
    def test_for_every_flag_the_dry_run_names_the_files_and_prints_the_config_the_real_run_writes(self):
        for flags in FLAGS:
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as d:
                dry, real = repo(d, "dry"), repo(d, "real")
                before, folders = files_of(real), folders_of(real)
                plan, _ = plan_of(dry, flags)
                said = aidd_here("init", "--dry-run", *flags, cwd=dry)
                self.assertEqual((said.returncode, files_of(dry)), (0, before), said.stderr + " (a dry run writes nothing)")
                self.assertEqual(folders_of(dry), folders, "a dry run makes no folder either")
                done = aidd_here("init", *flags, cwd=real)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                after = files_of(real)
                changed = {rel: text for rel, text in after.items() if before.get(rel) != text}
                self.assertEqual(sorted(plan.writes), sorted(changed), "the same file list")
                made = {"/".join(Path(rel).parts[:i]) for rel in changed for i in range(1, len(Path(rel).parts))}
                self.assertEqual(folders_of(real) - folders, made, "the real run makes the folders of the files it writes, and no more")
                for rel, text in changed.items():
                    self.assertEqual(plan.writes[rel], text, rel)
                self.assertEqual(plan.config, after[".aidd/config.yaml"], "the same config text")
                block = said.stdout.split("```yaml\n", 1)[1].split("```", 1)[0]
                self.assertEqual(block, after[".aidd/config.yaml"], "the dry run prints it")
                acts = ("wrote", "vendored", "linked", "updated", "appended")
                launcher = "~/.aidd/bin/aidd"  # in the home, shared by every repository here: another run may have written it between the two
                self.assertEqual(
                    [x for x in plan.actions if x.split(" ")[0] in acts and launcher not in x],
                    [x for x in done.stdout.splitlines() if x.split(" ")[0] in acts and launcher not in x],
                )
                for line in setup.dry_run_lines([x for x in plan.actions if x.split(" ")[0] in acts and launcher not in x]):
                    self.assertIn(line, said.stdout, "the dry run prints each line the real run prints, as what it would do")

    def test_every_file_the_plan_holds_is_named_in_the_dry_run_and_in_the_real_run(self):
        for flags in (["--harness", "codex"], ["--harness", "claude-code"], ["--harness", "codex", "--harness", "claude-code"]):
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as d:
                dry, real = repo(d, "dry"), repo(d, "real")
                plan, _ = plan_of(dry, flags)
                said = aidd_here("init", "--dry-run", *flags, cwd=dry).stdout
                done = aidd_here("init", *flags, cwd=real).stdout
                for rel in plan.writes:
                    if rel.startswith((".agents/", ".github/")):  # the skill's many files and the CI files are named by their folder
                        continue
                    self.assertIn(rel, said, f"the dry run names {rel}")
                    self.assertIn(rel, done, f"the real run names {rel}")
                self.assertEqual(said.count("would write .aidd/harness-rules.json"), 1, "once, however many agents")

    def test_a_dry_run_that_enables_the_plugins_in_claude_code_settings_makes_no_folder(self):
        """The plugins are installed (a plan takes the install as it would go), and the settings file that shares them with the
        project is written; a plan holds that write and the folder it goes in."""
        from unittest import mock

        for flags in (["--claude-plugins", "--harness", "claude-code"],):
            with (
                self.subTest(flags=flags),
                tempfile.TemporaryDirectory() as d,
                mock.patch.dict(os.environ, {"AIDD_OFFLINE": ""}),
                mock.patch("shutil.which", return_value="/usr/bin/claude"),
                mock.patch("aidd.setup.pins.stable_exists", return_value=None),
            ):
                root = repo(d)
                before = folders_of(root)
                plan, _ = plan_of(root, flags)
                self.assertIn(".claude/settings.json", plan.writes)
                self.assertEqual(folders_of(root), before)

    def test_a_dry_run_asks_github_nothing_and_makes_no_cache_folder(self):
        from unittest import mock

        from aidd.setup import pins

        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as cache:
            root = repo(d)
            for flags in ([], ["--claude-plugins"]):
                with (
                    mock.patch("aidd.setup.pins.installed_ref", return_value=None),  # an installed wheel, with no ref to pin
                    mock.patch("aidd.kernel.resources.cache_home", return_value=Path(cache) / "aidd"),
                    mock.patch("aidd.kernel.git.ls_remote", side_effect=AssertionError("a dry run asked GitHub")),
                    mock.patch.dict(os.environ, {"AIDD_OFFLINE": ""}),
                ):
                    plan, _ = plan_of(root, flags)
                self.assertEqual(os.listdir(cache), [], "no cache folder")
                line = next(x for x in plan.actions if x.startswith("pinned   the aidd workflow"))
                self.assertIn("latest release", line)
                self.assertIn("would pin the aidd workflow to the commit of the latest release", setup.dry_run_lines([line])[0])
            with self.assertRaises(AssertionError), mock.patch("aidd.kernel.git.ls_remote", side_effect=AssertionError("asked")):
                pins.remote_refs()  # outside a plan the same call does ask: the guard is the plan

    def test_no_line_of_a_preview_is_in_the_past_tense(self):
        for line, said in (
            ("wrote    .aidd/config.yaml", "would write .aidd/config.yaml"),
            ("risk     wrote the sensitive areas it found", "risk     would write the sensitive areas it found"),
            ("config   changed profile: team -> solo (--profile)", "config   would change profile: team -> solo (--profile)"),
            ("config   added   owners.specialists.legal: [x]", "config   would add   owners.specialists.legal: [x]"),
            ("config   dropped the comment `# x` inside owners", "config   would drop the comment `# x` inside owners"),
            ("kept     REVIEW.md (the repository's review policy)", "kept     REVIEW.md (the repository's review policy)"),
            ("hint     wrote nothing", "hint     wrote nothing"),
        ):
            self.assertEqual(setup.dry_run_lines([line]), [said])

    def test_a_flag_value_is_checked_in_the_dry_run_as_in_the_real_run(self):
        for flags in (
            ["--approvers", "@claude"],
            ["--environment", "production"],
            ["--environment", "Production=main"],
            ["--environment", "production=main", "--environment", "none"],
            ["--specialist", "security"],
            ["--test", "FOO=bar"],
            ["--ref", "main; rm -rf /"],
            ["--ci", "svn"],
            ["--profile", "tem"],
        ):
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as d:
                dry, real = repo(d, "dry"), repo(d, "real")
                said = aidd_here("init", "--dry-run", *flags, cwd=dry)
                done = aidd_here("init", *flags, cwd=real)
                self.assertEqual((said.returncode, said.stderr), (done.returncode, done.stderr))
                self.assertEqual(said.returncode, 2)
                self.assertEqual(files_of(dry), files_of(repo(d, "again")), "nothing written")

    def test_a_plan_holds_the_writes_and_reads_them_back_but_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "kept.txt").write_text("on disk\n", encoding="utf-8")
            with regular_files.holding_writes() as held:
                regular_files.write_text_safely(root, "kept.txt", "new\n")
                regular_files.write_text_safely(root, "sub/added.txt", "a\n")
                regular_files.write_text_safely(root, "sub/added.txt", "b\n", append=True)
                with regular_files.open_for_write(root / "settings.json", text=True, root=root) as out:
                    out.write("{}")
                self.assertEqual(regular_files.repository_text(root, "kept.txt"), "new\n")
                self.assertEqual(regular_files.named_text(root, "sub/added.txt"), ("a\nb\n", ""))
                self.assertTrue(regular_files.is_file_or_held(root, "settings.json"))
            self.assertEqual(held, {"kept.txt": "new\n", "sub/added.txt": "a\nb\n", "settings.json": "{}"})
            self.assertEqual(files_of(root), {"kept.txt": "on disk\n"})
            self.assertIsNone(regular_files.repository_text(root, "sub/added.txt"))

    def test_a_plan_refuses_a_write_through_a_link_as_the_real_run_does(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "r"
            root.mkdir()
            (Path(d) / "elsewhere").mkdir()
            (root / "dir").symlink_to(Path(d) / "elsewhere")
            with regular_files.holding_writes() as held:
                with self.assertRaises(regular_files.WriteRefused):
                    regular_files.write_text_safely(root, "dir/x.txt", "x\n")
            self.assertEqual(held, {})

    def test_a_dry_run_writes_nothing_outside_the_repository(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d) / "home"
            home.mkdir()
            root = repo(d)
            ran = subprocess.run(
                ["python3", "-m", "aidd", "init", "--dry-run", "--harness", "claude-code", "--harness", "codex"],
                cwd=root,
                env={**os.environ, "HOME": str(home), "XDG_CACHE_HOME": str(home / "cache"), "PYTHONPATH": src_pythonpath()},
                capture_output=True,
                text=True,
            )
            self.assertEqual(ran.returncode, 0, ran.stderr)
            self.assertEqual([p for p in home.rglob("*") if p.is_file() and "self-update" not in p.parts], [], "no launcher or settings in the home")
            self.assertIn("~/.aidd/bin/aidd", ran.stdout)


class DryRunDeletesNothingTests(unittest.TestCase):
    """A preview changes nothing: a deletion init or upgrade would make is named in the plan, and the file stays."""

    def adopted_with_allowed_tools(self, d: str) -> Path:
        root = repo(d)
        self.assertEqual(aidd_here("init", "--harness", "claude-code", cwd=root).returncode, 0)
        self.assertIn(mcp_wiring.ALLOWED_KEY, json.loads((root / ".aidd" / "harness-rules.json").read_text(encoding="utf-8")))
        config_file = root / ".aidd" / "config.yaml"
        config_file.write_text(config_file.read_text(encoding="utf-8") + "\nmcp:\n  allow_own_tools: false\n", encoding="utf-8")
        return root

    def test_the_dry_run_names_the_ledger_rewrite_and_leaves_the_file(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.adopted_with_allowed_tools(d)
            before = files_of(root)
            plan, _ = plan_of(root, ["--harness", "claude-code"])
            self.assertNotIn(".aidd/harness-rules.json", plan.removals, "the ask rules it lists stay")
            self.assertNotIn(mcp_wiring.ALLOWED_KEY, json.loads(plan.writes[".aidd/harness-rules.json"]))
            self.assertIn("updated  .aidd/harness-rules.json (no MCP tool of aidd's is listed now)", plan.actions)
            said = aidd_here("init", "--dry-run", "--harness", "claude-code", cwd=root)
            self.assertIn("would update .aidd/harness-rules.json (no MCP tool of aidd's is listed now)", said.stdout)
            self.assertEqual(files_of(root), before, "the file is unchanged, and nothing else changed")
            done = aidd_here("init", "--harness", "claude-code", cwd=root)
            self.assertIn("updated  .aidd/harness-rules.json (no MCP tool of aidd's is listed now)", done.stdout)
            self.assertNotIn(
                mcp_wiring.ALLOWED_KEY,
                json.loads((root / ".aidd" / "harness-rules.json").read_text(encoding="utf-8")),
                "the real run writes what the plan named",
            )

    def test_an_upgrade_without_yes_leaves_the_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.adopted_with_allowed_tools(d)
            before = files_of(root)
            said = aidd_here("upgrade", cwd=root)
            self.assertEqual(said.returncode, 0, said.stderr)
            self.assertEqual(files_of(root), before)

    def test_a_plan_reads_a_removed_file_as_missing_and_a_later_write_brings_it_back(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "gone.txt").write_text("x\n", encoding="utf-8")
            with regular_files.holding_writes() as held:
                self.assertTrue(regular_files.hold_removal(root, "gone.txt"))
                self.assertEqual(regular_files.named_text(root, "gone.txt"), (None, regular_files.MISSING))
                self.assertFalse(regular_files.is_file_or_held(root, "gone.txt"))
                self.assertEqual(regular_files.held_removals(), ["gone.txt"])
                regular_files.write_text_safely(root, "gone.txt", "y\n")
                self.assertEqual((regular_files.repository_text(root, "gone.txt"), regular_files.held_removals()), ("y\n", []))
            self.assertEqual((root / "gone.txt").read_text(encoding="utf-8"), "x\n")
            self.assertEqual(held, {"gone.txt": "y\n"})


if __name__ == "__main__":
    unittest.main()
