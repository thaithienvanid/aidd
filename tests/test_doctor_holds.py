"""`aidd doctor` reports every action whose ask no rule holds in a wired harness, and says where each harness's rules do not hold.

The invariant: for each harness that takes ask rules and each `ask` action, either a command the action's patterns stand for
is asked by the harness as its file is written (matched the way its harness documents, by `test_risk`'s emulations), or
doctor names the action as one only the skill asks for. The sample commands come from the patterns, never from doctor's own
counts. Doctor also names, for each harness, the mode its rules hold in and every documented mode where they do not, with
the page and the date read, and the generated tables say the same.
"""

import json
import re
import tempfile
import tomllib
import unittest
from pathlib import Path

import shared_reads
import test_risk
from helpers import ROOT, git

from aidd import config, risk
from aidd.risk import harness_rules, jsonc
from aidd.docsgen import ask_holds
from aidd.setup import adoption, ask_rules, doctor_harnesses

KEYS = [key for key, h in config.HARNESSES.items() if h.ask_rules]
EMULATE = test_risk.EachHarnessAsksWhatItsFormatCanHold
CONFIGS = {
    "built-in": "",
    "pr.merge allowed": "risks:\n  rules:\n    - {action: pr.merge, level: allow}\n",
    "a custom action asks": "risks:\n  actions:\n    cloud.launch: {commands: ['zzcloud launch*'], description: x}\n  rules:\n    - {action: cloud.launch, level: ask}\n",
}


def samples(pattern: str) -> list[str]:
    """Commands a pattern stands for: each `*` is empty, a word, or a remote."""
    return list(dict.fromkeys(pattern.replace("*", fill) for fill in ("", "x", "origin")))


def asker(root: Path, key: str):
    """What the harness `key` asks, read from the file aidd wrote, as its harness matches a command."""
    fmt = config.HARNESSES[key].ask_rules
    bash = lambda e: e[len("Bash(") : -1]  # noqa: E731
    load = lambda rel: jsonc.loads((root / rel).read_text(encoding="utf-8"), "jsonc")  # noqa: E731  (a person's file may hold comments)
    if fmt in ("claude-code", "qwen"):
        rel = risk.FORMATS[fmt].path
        entries = [bash(e) for e in load(rel)["permissions"]["ask"] if e.startswith("Bash(")]
        return (lambda c: EMULATE.claude_code_asks(entries, c)) if fmt == "claude-code" else (lambda c: EMULATE.glob_asks(entries, c))
    if fmt == "grok":
        entries = [bash(e) for e in tomllib.loads((root / ".grok/config.toml").read_text())["permission"]["ask"] if e.startswith("Bash(")]
        return lambda c: EMULATE.claude_code_asks(entries, c)
    if fmt == "opencode":
        rel = next(r for r in risk.rule_files("opencode") if (root / r).exists())
        entries = [r["resource"] for r in load(rel)["permissions"] if r["effect"] == "ask" and r["action"] == "shell"]
        return lambda c: EMULATE.glob_asks(entries, c)
    if fmt == "vscode":
        keys = load(".vscode/settings.json")["chat.tools.terminal.autoApprove"]
        regexes = [k[1:-1] for k, v in keys.items() if v is False]
        return lambda c: any(re.search(r, c) for r in regexes)
    rules = [json.loads(m) for m in re.findall(r"pattern = (\[.*?\]), decision", (root / ".codex/rules/aidd.rules").read_text())]
    return lambda c: EMULATE.words_ask(rules, c)


class DoctorNamesWhatNoRuleHolds(unittest.TestCase):
    def repo(self, key: str, extra: str) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        git(root, "init", "-q", "-b", "main")
        (root / ".aidd").mkdir()
        (root / ".aidd" / "config.yaml").write_text('aidd_version: "1.0.0"\nprofile: solo\n' + extra, encoding="utf-8")
        adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=[key]))
        return root

    def test_every_asking_action_is_held_by_a_rule_or_named_by_doctor(self):
        for name, extra in CONFIGS.items():
            for key in KEYS:
                with self.subTest(config=name, harness=key):
                    root = self.repo(key, extra)
                    cfg = config.load_file(config.CONFIG_PATH, str(root))
                    rs = risk.rule_set(cfg)
                    asks = asker(root, key)
                    with shared_reads.shared_git_reads(root):  # nothing below writes the repository, so each ref and setting is read once
                        branches = ask_rules.push_rule_branches(root)
                        checks = doctor_harnesses.harness_checks(root, [key])
                    labelled = harness_rules.labelled_patterns(rs, branches)  # a pattern two actions serve is held for each
                    asked_patterns = set(risk.harness_patterns(rs, branches))
                    api = risk.api_write_patterns()
                    holds_by_emulation = {}
                    for action in dict.fromkeys(r.action for r in rs.rules if r.level == "ask"):
                        patterns = [p for a, p in labelled if a == action and p in asked_patterns]
                        patterns += api if (rs.actions.get(action) or {}).get("api_endpoints") else []
                        held = any(asks(c) for p in patterns for c in samples(p))
                        reads = (rs.actions.get(action) or {}).get("file_reads")
                        held = held or bool(reads and risk.FORMATS[str(config.HARNESSES[key].ask_rules)].reads)
                        holds_by_emulation[action] = held
                    said = "\n".join(m for _, m in checks)
                    line = next((m for _, m in checks if "no rule of its own holds" in m), "")
                    for action, held in holds_by_emulation.items():
                        self.assertEqual(f"`{action}`" in line, not held, (action, line))
                        if not held:
                            self.assertIn("the skill alone asks", line)
                    self.assertIn("its ask rules hold in", said)

    def test_every_harness_says_its_mode_and_every_documented_limit_with_its_source(self):
        for key in KEYS:
            with self.subTest(harness=key):
                h = config.HARNESSES[key]
                self.assertTrue(h.asks_in and h.limits is not None, "the data names the mode its rules hold in")
                root = self.repo(key, "")
                said = "\n".join(m for _, m in doctor_harnesses.harness_checks(root, [key]))
                self.assertIn(h.asks_in, said)
                for limit in h.limits:
                    self.assertIn(limit.what, said)
                    self.assertIn(limit.source, said)
                    self.assertRegex(limit.read, r"^\d{4}-\d{2}-\d{2}$")
                    self.assertEqual("unconfirmed: " + limit.what in said, not limit.confirmed)

    def test_the_docs_table_says_the_same(self):
        table = ask_holds.ask_rules_table()
        guide = (ROOT / "docs" / "GUIDE.md").read_text(encoding="utf-8")
        for key in KEYS:
            h = config.HARNESSES[key]
            self.assertIn(h.asks_in, table)
            for limit in h.limits:
                self.assertIn(limit.source, table)
                self.assertIn(limit.what, table)
        self.assertIn(table, guide, "GUIDE.md holds the generated table")
        self.assertNotRegex(guide.lower(), r"every harness above asks for the same commands")

    def test_a_push_that_names_no_branch_is_said_in_the_table_and_by_doctor(self):
        row = next(r for r in ask_holds.ask_holds_table().splitlines() if r.startswith("| `git.push` "))
        self.assertIn(risk.UNHELD["git.push"], row)
        root = self.repo("claude-code", "")
        self.assertTrue([m for _, m in doctor_harnesses.harness_checks(root, ["claude-code"]) if risk.UNHELD["git.push"] in m])
        # and it is true: no pattern any format writes matches a push that names no branch
        for key in KEYS:
            asks = asker(self.repo(key, ""), key)
            self.assertFalse(asks("git push"), key)
            self.assertFalse(asks("git push origin HEAD"), key)

    def test_the_holds_table_names_who_reads_the_visual_studio_code_rules(self):
        self.assertIn("VS Code's Copilot agent", risk.api_harness_names())
        self.assertNotIn("GitHub Copilot", risk.api_harness_names())


if __name__ == "__main__":
    unittest.main()
