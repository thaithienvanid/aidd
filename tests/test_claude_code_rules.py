"""Claude Code reads `:*` as its older prefix form only at the end of a pattern (`ls:*` is `ls *`), and a colon in the
middle is a literal (its permissions docs, read 2026-11-08). So a trailing `db:*` would read as `db *` and miss
`rails db:migrate`: aidd writes it as `db*`, which asks more, never less. A trailing `:*` that starts a word has no form,
so it is left to the skill, and `aidd doctor` names it (R413). Grok Build gets the same forms. aidd's own block comes
first in `permissions.ask`, and its `Read(!...)` carve-outs follow its read rules, so a carve-out lifts only aidd's rules,
never a person's own."""

from __future__ import annotations

import json
import tempfile
import tomllib
import unittest
from pathlib import Path

import helpers  # noqa: F401  # the hermetic environment
from aidd import risk
from aidd.kernel import globs
from aidd.risk import harness_rules


def written(fmt: str, root: Path) -> list[str]:
    rs = risk.rule_set(None)
    risk.apply_harness_rules(root, fmt, risk.harness_patterns(rs, "main"), read_paths=risk.harness_read_paths(rs))
    if fmt == "grok":
        return tomllib.loads((root / ".grok/config.toml").read_text())["permission"]["ask"]
    return json.loads((root / harness_rules.FORMATS[fmt].path).read_text())["permissions"]["ask"]


class NoRuleEndsInAColonStar(unittest.TestCase):
    def test_no_rule_aidd_writes_ends_in_a_colon_star(self):
        for fmt in ("claude-code", "grok"):
            with tempfile.TemporaryDirectory() as d:
                rules = written(fmt, Path(d))
            self.assertTrue(rules)
            for rule in rules:
                with self.subTest(fmt=fmt, rule=rule):
                    self.assertFalse(rule.endswith(":*)"))

    def test_each_form_asks_at_least_where_the_pattern_does(self):
        cases = [
            ("rails db:*RAILS_ENV=production*", "rails db:*RAILS_ENV=production*", ["rails db:migrate RAILS_ENV=production"]),
            ("RAILS_ENV=production rails db:*", "RAILS_ENV=production rails db*", ["RAILS_ENV=production rails db:drop"]),
            ("git push --force*", "git push --force*", ["git push --force origin main"]),
            ("git push * :*", None, []),  # a trailing `:*` that starts a word has no form: the skill asks
        ]
        for pattern, form, commands in cases:
            with self.subTest(pattern=pattern):
                self.assertEqual(harness_rules.claude_code_form(pattern), form)
                for command in commands:
                    self.assertTrue(globs.match_text(pattern, command))
                    self.assertTrue(globs.match_text(str(form), command))

    def test_a_pattern_with_no_form_is_named_for_doctor(self):
        patterns = risk.harness_patterns(risk.rule_set(None), "main")
        for fmt in ("claude-code", "grok"):
            with self.subTest(fmt=fmt):
                gaps = risk.unwritten(fmt, patterns)
                self.assertEqual(gaps, [p for p in patterns if harness_rules.claude_code_form(p) is None])
                self.assertIn("git push * :*", gaps)


def asks(rules: list[str], path: str) -> bool:
    """Whether Claude Code's Read tool asks for `path` under `rules`, read in gitignore order: the last read rule that
    matches decides, and a `!` rule carves its path out of the rules before it."""
    state = False
    for rule in rules:
        if rule.startswith("Read(") and globs.match(rule[5:-1].lstrip("!"), path):
            state = not rule.startswith("Read(!")
    return state


class TheCarveOutsLiftOnlyAiddsOwnReadRules(unittest.TestCase):
    """The R407 re-review L1: a `Read(!...)` rule carves its paths out of the rules listed before it, from the same file.
    So aidd's block comes first, and a person's own entry stays after it, even when it is the same as one of aidd's."""

    def apply(self, theirs: list[str]) -> tuple[list[str], list[str], Path]:
        rs = risk.rule_set(None)
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        root = Path(d)
        (root / ".claude").mkdir()
        (root / ".claude/settings.json").write_text(json.dumps({"permissions": {"ask": theirs}}))
        done = risk.apply_harness_rules(root, "claude-code", risk.harness_patterns(rs, "main"), read_paths=risk.harness_read_paths(rs))
        return json.loads((root / ".claude/settings.json").read_text())["permissions"]["ask"], done, root

    def test_claude_code_carves_the_env_templates_and_code_out_after_aidd_s_read_rules(self):
        with tempfile.TemporaryDirectory() as d:
            rules = written("claude-code", Path(d))
        carve = [r for r in rules if r.startswith("Read(!")]
        self.assertEqual(carve[:4], [f"Read(!**/.env.{s})" for s in ("example", "sample", "template", "dist")])
        self.assertIn("Read(!**/*.py)", carve)  # code, such as credentials.py, which `aidd risk` allows too
        first = min(rules.index(c) for c in carve)
        self.assertFalse([r for r in rules[first:] if r.startswith("Read(") and not r.startswith("Read(!") and r != "Read(**/secrets.*)"])
        self.assertEqual(rules[-1], "Read(**/secrets.*)")  # the re-include, after the carve-outs

    def test_each_carve_out_is_a_file_aidd_risk_allows(self):
        rs = risk.rule_set(None)
        for path in [p[1:] for p in risk.harness_read_paths(rs) if p.startswith("!")]:
            with self.subTest(path=path):
                self.assertEqual(risk.command_level(rs, f"cat {path.replace('**/', 'config/').replace('*', 'credentials')}")["level"], "allow")

    def test_a_person_s_own_entry_stays_after_every_carve_out(self):
        """The final security confirm of f7fdec0: a person's copy of one of aidd's rules was merged into aidd's block,
        ahead of the carve-outs, which then lifted it. It stays in its own place now, so it still asks."""
        cases = [
            (["Read(**/.env.*)"], "Read(!**/*.ts)", "config/.env.ts"),
            (["Read(**/secrets/**)"], "Read(!**/*.py)", "src/secrets/client.py"),
            (["Read(**/credentials.*)", "Bash(make deploy)"], "Read(!**/*.py)", "src/credentials.py"),
            (["Read(**/.env*)"], "Read(!**/.env.example)", ".env.example"),
        ]
        for theirs, carve, path in cases:
            with self.subTest(theirs=theirs):
                rules, done, root = self.apply(theirs)
                self.assertEqual(rules[-len(theirs) :], theirs)
                self.assertGreater(len(rules) - len(theirs), rules.index(carve))
                self.assertTrue(asks(rules, path))
                rs = risk.rule_set(None)
                again = risk.apply_harness_rules(root, "claude-code", risk.harness_patterns(rs, "main"), read_paths=risk.harness_read_paths(rs))
                self.assertFalse([line for line in again if not line.startswith("kept")])
                self.assertEqual(json.loads((root / ".claude/settings.json").read_text())["permissions"]["ask"], rules)
                risk.remove_harness_rules(root)
                self.assertEqual(json.loads((root / ".claude/settings.json").read_text())["permissions"]["ask"], theirs)

    def test_without_a_rule_of_the_person_s_the_carve_outs_hold(self):
        rules, _, _ = self.apply(["Bash(make deploy)"])
        for path, want in (
            (".env", True),
            (".env.example", False),
            ("src/credentials.py", False),
            ("config/settings/secrets.py", True),  # the re-include wins over the code carve-out
            ("include/secrets.h", True),
            ("config/credentials.json", True),
        ):
            with self.subTest(path=path):
                self.assertEqual(asks(rules, path), want)

    def test_no_other_format_gets_a_carve_out(self):
        for fmt in ("qwen", "grok"):
            with self.subTest(fmt=fmt), tempfile.TemporaryDirectory() as d:
                self.assertFalse([r for r in written(fmt, Path(d)) if r.startswith("Read(!")])


if __name__ == "__main__":
    unittest.main()
