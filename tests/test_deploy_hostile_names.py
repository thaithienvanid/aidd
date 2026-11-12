"""Text read from the repository reaches the written config and init's output only as data: a workflow's
path, an `environment:` name, and a branch or tag pattern may hold a new line, a carriage return, an escape, a `#`, a `: `, or a
leading `-`. Each must give a config that loads back with exactly the environments expected and nothing else, and output with
no control character in it."""

import re
import tempfile
import unittest
from pathlib import Path

from helpers import aidd_here, git

from aidd import config

CONTROL = re.compile(r"[\x00-\x09\x0b-\x1f\x7f-\x9f‪-‮⁦-⁩]")
GOOD = ("good.yml", "on:\n  push:\n    branches: [main]\njobs:\n  ship:\n    environment: production\n    steps: []\n")
PRODUCTION = {"name": "production", "branches": ["main"]}


def workflow(branches: str = "[main]", environment: str = "production") -> str:
    return f"on:\n  push:\n    branches: {branches}\njobs:\n  ship:\n    environment: {environment}\n    steps: []\n"


# name: (the file name, its text, the environments init writes)
CASES = {
    "a new line in the path": ("evil\nrisks: {rules: []}\n#.yml", workflow(), [PRODUCTION]),
    "a carriage return in the path": ("evil\rrisks: x.yml", workflow(), [PRODUCTION]),
    "an escape in the path": ("evil\x1b[2Jx.yml", workflow(), [PRODUCTION]),
    "a # in the path": ("evil # risks.yml", workflow(), [PRODUCTION]),
    "a colon and space in the path": ("evil: risks.yml", workflow(), [PRODUCTION]),
    "a leading dash in the path": ("-evil.yml", workflow(), [PRODUCTION]),
    "an escape in the environment name": ("e.yml", workflow(environment="'stage\x1b[2J'"), [PRODUCTION, {"name": "stage-2j", "branches": ["main"]}]),
    "a # in the environment name": ("e.yml", workflow(environment="'a#b'"), [PRODUCTION, {"name": "a", "branches": ["main"]}]),
    "a colon and space in the environment name": ("e.yml", workflow(environment="'a: b'"), [PRODUCTION, {"name": "a-b", "branches": ["main"]}]),
    "a leading dash in the environment name": ("e.yml", workflow(environment="'- c'"), [PRODUCTION, {"name": "c", "branches": ["main"]}]),
    "a carriage return in the environment name": ("e.yml", workflow(environment="x\rrisks: y"), [PRODUCTION, {"name": "x", "branches": ["main"]}]),
    "an escape in a branch": ("e.yml", workflow(branches="[main, 'a\x1b[2Jb']"), [PRODUCTION]),
    "a colon and space in a branch": ("e.yml", workflow(branches="[main, 'a: b']"), [PRODUCTION]),
    "a # in a branch": ("e.yml", workflow(branches="[main, 'a#b']"), [{"name": "production", "branches": ["main", "a#b"]}]),
    "a leading dash in a branch": ("e.yml", workflow(branches="[main, '-b']"), [{"name": "production", "branches": ["main", "-b"]}]),
}


class HostileNamesTests(unittest.TestCase):
    def init(self, files: dict[str, str], *flags: str):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve() / "repo"
            (root / ".github/workflows").mkdir(parents=True)
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.name", "Maya Lee")
            git(root, "config", "user.email", "maya@users.noreply.github.com")
            git(root, "commit", "-q", "--allow-empty", "-m", "start")
            for name, text in files.items():
                (root / ".github/workflows" / name).write_bytes(text.encode("utf-8"))
            args = ("init", ".", "--profile", "solo", "--ci", "none", "--harness", "claude-code", *flags)
            dry = aidd_here(*args, "--dry-run", cwd=root)
            real = aidd_here(*args, cwd=root)
            cfg = config.load_file(config.CONFIG_PATH, str(root))
            return cfg, (root / config.CONFIG_PATH).read_text(encoding="utf-8"), dry, real

    def test_a_hostile_name_gives_the_environments_expected_and_nothing_else(self):
        for name, (file, text, want) in CASES.items():
            with self.subTest(name):
                cfg, written, dry, real = self.init({GOOD[0]: GOOD[1], file: text})
                self.assertEqual((dry.returncode, real.returncode), (0, 0), dry.stderr + real.stderr)
                self.assertEqual(sorted(cfg.get("environments"), key=lambda e: e["name"]), sorted(want, key=lambda e: e["name"]))
                self.assertIsNone(cfg.get("risks"), "no line of the file reached the config as a key")
                for label, shown in (("the config", written), ("the dry run", dry.stdout), ("the real run", real.stdout)):
                    self.assertIsNone(CONTROL.search(shown), f"{label} holds a control character: {CONTROL.search(shown)}")

    def test_a_workflow_it_cannot_copy_is_named_as_data_in_the_hint(self):
        """With no safe workflow to write, the unsafe one is said in one line, its control characters made spaces."""
        cfg, written, dry, real = self.init({"evil\x1b[2J\nrisks.yml": workflow()})
        self.assertIsNone(cfg.get("environments"))
        hint = [ln for ln in real.stdout.splitlines() if ln.startswith("hint     your workflows deploy:")]
        self.assertEqual(len(hint), 1, real.stdout)
        self.assertIn("evil [2J risks.yml:6", hint[0])
        self.assertIsNone(CONTROL.search(real.stdout))

    def test_doctor_and_the_host_file_note_show_a_hostile_path_without_its_control_characters(self):
        from aidd import delegation, risk
        from aidd.setup import delegation_wiring

        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            git(root, "init", "-q", "-b", "main")
            (root / ".github/workflows").mkdir(parents=True)
            (root / ".github/workflows/evil\x1b[2J\nx.yml").write_bytes(workflow().encode())
            (root / "a\x1b[2J\n").mkdir()
            (root / "a\x1b[2J\n/vercel.json").write_text("{}", encoding="utf-8")
            git(root, "add", "-A")
            shown = [*delegation.workflows_deploying_on(root, "main", risk.rule_set(None)), *delegation_wiring.deploy_files(root)]
            self.assertEqual(len(shown), 2, shown)
            for line in shown:
                self.assertIsNone(CONTROL.search(line), repr(line))

    def test_the_comment_cannot_end_its_line_whatever_it_is_given(self):
        from aidd.setup import config_template

        template = config_template.ConfigTemplate(
            "solo",
            environments=[PRODUCTION],
            environments_read={"production": (".github/workflows/x\nrisks: {rules: []}\n", "y\r\x1b[2Jz")},
        )
        text = config_template.environments_text(template)
        self.assertEqual(config.load_text('aidd_version: "1.0.0"\nprofile: solo\n' + text).get("environments"), [PRODUCTION])
        self.assertIsNone(CONTROL.search(text))
        self.assertEqual(len([ln for ln in text.splitlines() if ln.startswith("  # read from")]), 1)


if __name__ == "__main__":
    unittest.main()
