"""For every harness and every action, the commands that ask never become fewer: not by where aidd writes, not by what a person's
file holds, not by a rule added elsewhere, and not except where the harness's own format cannot hold a pattern.

The commands are generated from the writers, never listed: each command pattern of every action stands for sample commands, and
the file each writer leaves is read back as its harness matches (`test_doctor_holds.asker`). The properties:

1. every pattern the format can hold (`risk.unwritten` does not list it) has a sample the written file asks for;
2. the asked set a person's real-shaped file ends with holds every command an empty folder's file asks for;
3. a rule added in the config adds asks and removes none, in every format.
"""

import contextlib
import tempfile
import unittest
from pathlib import Path

import test_doctor_holds as oracle
from helpers import git

from aidd import config, risk
from aidd.setup import adoption, ask_rules

KEYS = oracle.KEYS
EXTRA = "risks:\n  actions:\n    cloud.launch: {commands: ['zzcloud launch*', 'zzcloud destroy *'], description: x}\n  rules:\n    - {action: cloud.launch, level: ask}\n"
# A person's own settings file for each harness that takes comments, with a comment, a trailing comma, and a setting of theirs.
THEIRS = {
    "copilot": (".vscode/settings.json", '// mine\n{\n  "editor.tabSize": 2, // two\n  "chat.tools.terminal.autoApprove": {"npm test": true,},\n}\n'),
    "opencode": ("opencode.jsonc", '{\n  // mine\n  "theme": "dark",\n  "permissions": [{"action": "shell", "resource": "*", "effect": "allow"},],\n}\n'),
    "qwen-code": (".qwen/settings.json", '{\n  // mine\n  "model": "x" /* pinned */,\n  "permissions": {"allow": ["Bash(ls)"]}\n}\n'),
}


def every_sample(rs) -> list[str]:
    """Commands that every pattern of every action stands for, `gh api` set included."""
    patterns = [c for spec in rs.actions.values() for c in spec.get("commands", [])] + risk.api_write_patterns()
    return sorted({s for p in patterns for s in oracle.samples(p)})


def asked_set(root: Path, key: str, commands: list[str]) -> set[str]:
    asks = oracle.asker(root, key)
    return {c for c in commands if asks(c)}


class TheAskedCommandsNeverShrink(unittest.TestCase):
    def repo(self, key: str, extra: str = "") -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        git(root, "init", "-q", "-b", "main")
        (root / ".aidd").mkdir()
        (root / ".aidd" / "config.yaml").write_text('aidd_version: "1.0.0"\nprofile: solo\n' + extra, encoding="utf-8")
        adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=[key]))
        return root

    def rules(self, root: Path):
        return risk.rule_set(config.load_file(config.CONFIG_PATH, str(root)))

    def test_every_pattern_a_format_can_hold_is_asked_in_the_file_it_writes(self):
        for extra in ("", EXTRA):
            for key in KEYS:
                with self.subTest(harness=key, config=bool(extra)):
                    root = self.repo(key, extra)
                    rs, branches = self.rules(root), ask_rules.push_rule_branches(root)
                    fmt = str(config.HARNESSES[key].ask_rules)
                    patterns = risk.harness_patterns(rs, branches)
                    gaps = set(risk.unwritten(fmt, patterns))
                    asks = oracle.asker(root, key)
                    missed = [p for p in patterns if p not in gaps and not any(asks(c) for c in oracle.samples(p))]
                    self.assertEqual(missed, [], "a pattern the format holds has no ask in its file")
                    if fmt in ("vscode", "opencode"):
                        self.assertEqual(gaps, set(), "these formats hold every pattern")
                    if fmt in ("claude-code", "grok"):
                        self.assertTrue(all(p.endswith(" :*") for p in gaps), gaps)

    def test_a_persons_real_shaped_file_ends_with_every_ask_an_empty_folder_gets(self):
        for key, (rel, text) in THEIRS.items():
            with self.subTest(harness=key):
                clean = self.repo(key)
                rs = self.rules(clean)
                commands = every_sample(rs)
                want = asked_set(clean, key, commands)
                tmp = tempfile.TemporaryDirectory()
                self.addCleanup(tmp.cleanup)
                root = Path(tmp.name)
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_bytes(text.encode("utf-8"))
                fmt = str(config.HARNESSES[key].ask_rules)
                risk.apply_harness_rules(root, fmt, risk.harness_patterns(rs, ask_rules.push_rule_branches(clean)), read_paths=risk.harness_read_paths(rs))
                got = asked_set(root, key, commands)
                self.assertEqual(sorted(want - got), [], "the person's file lost an ask")
                self.assertEqual(want, got, "and gained none either: the same rules")

    def test_a_rule_added_in_the_config_removes_no_ask_in_any_format(self):
        for key in KEYS:
            with self.subTest(harness=key):
                base, more = self.repo(key), self.repo(key, EXTRA)
                commands = every_sample(self.rules(more))
                before, after = asked_set(base, key, commands), asked_set(more, key, commands)
                self.assertEqual(sorted(before - after), [])
                self.assertTrue(after > before or key in ("codex", "qwen-code") and after >= before, "the new action asks something")

    def test_the_files_stay_the_same_asks_through_an_upgrade_and_a_second_init(self):
        for key in KEYS:
            with self.subTest(harness=key):
                root = self.repo(key)
                commands = every_sample(self.rules(root))
                before = asked_set(root, key, commands)
                with contextlib.chdir(root):
                    adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=[key]))
                self.assertEqual(asked_set(root, key, commands), before)


if __name__ == "__main__":
    unittest.main()
