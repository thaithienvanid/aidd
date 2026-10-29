"""`aidd uninstall --yes` right after `aidd init` leaves the repository as it was: the config init wrote counts as
unchanged whatever init detected and wrote into it, and aidd's output folders in .aidd/ go too. A person's edit is
kept."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from helpers import git

from aidd import config
from aidd.setup import adoption, config_template, detection, hook_wiring, uninstalling


def init_as_the_cli_does(root: Path) -> None:
    """`aidd init` with what it detects in `root` (cli/commands/setup.py), and a goal and a compliance target."""
    found = detection.detect(root)
    tests = next((t["test"] for t in found["tests"] if t["path"] == "."), None)
    adoption.init(
        root,
        adoption.InitOptions(
            profile="solo",
            ci="none",
            links=[],
            approvers=["email:dev@example.com"],
            test=tests or config_template.SMOKE_TEST,
            goal="Every order ships on the day it is paid",
            harnesses=["claude-code"],
            risk_rules=[*found["risk_rules"], {"name": "payments", "paths": ["src/payments/**"], "dimensions": ["financial"]}],
            stack=detection.stack_radar(found),
            ui=not found["no_ui"],
            existing_code=found["existing_code"],
            compliance_targets=["soc2"],
            held_commands=[*found["held_commands"], {"name": "held: release", "match": ["npm run release*"], "message": "held for a person: it publishes"}],
        ),
    )


@unittest.skipUnless(shutil.which("git"), "git is required")
def git_ok(root: Path, *args: str) -> bool:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True).returncode == 0


class UninstallLeavesNothingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(shutil.rmtree, Path(os.environ["HOME"]) / ".aidd", True)
        self.root = Path(self.tmp.name) / "shop"
        (self.root / "src" / "auth").mkdir(parents=True)
        (self.root / "migrations").mkdir()
        (self.root / "package.json").write_text(
            json.dumps({"name": "shop", "scripts": {"test": "vitest run", "deploy": "wrangler deploy"}, "devDependencies": {"vitest": "1"}}), encoding="utf-8"
        )
        (self.root / "compose.yaml").write_text("services:\n  web:\n    image: shop\n", encoding="utf-8")
        (self.root / "src" / "auth" / "login.ts").write_text("export {}\n", encoding="utf-8")
        (self.root / "migrations" / "001.sql").write_text("select 1;\n", encoding="utf-8")
        git(self.root, "init", "-q")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "the shop")
        init_as_the_cli_does(self.root)
        self.cfg = self.root / ".aidd" / "config.yaml"

    def test_the_config_init_wrote_counts_as_unchanged(self):
        text = self.cfg.read_text(encoding="utf-8")
        for written in ("goal: ", "stack:", "preview:", "targets: [soc2]", "held_commands:", "risk_rules:"):  # what init detected, written in
            self.assertIn(written, text)
        self.assertTrue(config_template.written_by_init(text))
        actions = uninstalling.uninstall(self.root)
        self.assertIn("would remove .aidd/config.yaml", [a.replace(str(self.root) + "/", "") for a in actions])

    def test_an_edit_init_could_not_have_made_keeps_the_config(self):
        edits = (
            lambda t: t.replace("# The project's technology radar", "# Our radar"),  # a comment
            lambda t: t.replace('# protected_paths: ["scripts/release/**"]', 'protected_paths: ["scripts/**"]'),  # a field
        )
        for edit in edits:
            text = edit(self.cfg.read_text(encoding="utf-8"))
            self.assertNotEqual(text, self.cfg.read_text(encoding="utf-8"))
            self.assertFalse(config_template.written_by_init(text))
        self.assertFalse(config_template.written_by_init("profile: [not, a, profile]\n"))

    def test_uninstall_after_init_leaves_the_repository_as_it_was(self):
        for rel in uninstalling.OUTPUT_DIRS:  # what aidd test, the pages, and the verifier write
            (self.root / rel / "x").mkdir(parents=True)
            (self.root / rel / "x" / "out.json").write_text("{}\n", encoding="utf-8")
        uninstalling.uninstall(self.root, yes=True)
        self.assertFalse((self.root / ".aidd").exists())
        self.assertEqual(git(self.root, "status", "--porcelain", "--ignored").strip(), "")

    def test_the_output_folders_are_ignored_and_only_folders(self):
        # A file directly in .aidd/ is committed; a folder in it is aidd's output, which the one .gitignore line ignores.
        self.assertEqual(adoption.GITIGNORE_LINE, config.OUTPUT_IGNORE)
        for rel in uninstalling.OUTPUT_DIRS:
            self.assertEqual(Path(rel).parent, Path(".aidd"))
            (self.root / rel).mkdir(parents=True)
            (self.root / rel / "evidence.json").write_text("{}\n", encoding="utf-8")
            self.assertTrue(git_ok(self.root, "check-ignore", "-q", f"{rel}/evidence.json"), rel)
        self.assertFalse(git_ok(self.root, "check-ignore", "-q", config.CONFIG_PATH))

    def test_the_guard_log_is_in_the_git_directory(self):
        self.assertTrue(config.guard_log(self.root).is_relative_to((self.root / ".git").resolve()))
        self.assertEqual(config.guard_log(self.root).parent, config.state_dir(self.root))


@unittest.skipUnless(os.name != "nt", "the user launcher is a POSIX script")
class UserLauncherHomeTests(unittest.TestCase):
    def test_init_makes_a_home_folder_that_does_not_exist_yet(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d) / "new" / "home"
            with unittest.mock.patch.dict(os.environ, {"HOME": str(home)}):
                actions: list[str] = []
                hook_wiring.install_user_launcher(Path(d), hook_wiring.launcher(), actions)
                self.assertIsNotNone(hook_wiring.read_user_launcher()[0], actions)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root writes anywhere")
    def test_a_home_it_cannot_write_warns_and_init_goes_on(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d) / "home"
            home.mkdir(mode=0o555)
            try:
                with unittest.mock.patch.dict(os.environ, {"HOME": str(home)}):
                    actions: list[str] = []
                    hook_wiring.install_user_launcher(Path(d), hook_wiring.launcher(), actions)
            finally:
                home.chmod(0o755)
            self.assertTrue(actions[0].startswith("warn     could not write ~/.aidd/bin/aidd"), actions)


if __name__ == "__main__":
    unittest.main()
