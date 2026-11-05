"""A budget for the harness ask rules that widen: a leading-words format (Codex, Qwen Code) asks at a
pattern's leading words when it has no wildcard, so it asks before more commands than the rule names. Each widened
prefix, and each byte of the rules a harness holds, makes its prompts and its file grow, so a new one must not slip in.
The caps were set on 2026-11-06 at what the built-in risk rules give today, and hold with the headroom of
tests/budgets.py. A new widened prefix is the cue to give that pattern a leading-words form of its own (see
`harness_rules.leading_words`) or to say, here, why the cap rises."""

import tempfile
import unittest
from pathlib import Path

import budgets
import helpers  # noqa: F401  (puts src on sys.path)
from aidd import risk
from aidd.risk import harness_rules

# Widened prefixes per leading-words format.
WIDENED_CAP = 17
# The bytes of the rules file aidd writes for each leading-words format. They rose on 2026-11-07 by the four `gh repo` patterns of
# `repo.settings.change`, a command each format can hold. Qwen Code rose on 2026-11-08 by the `Read(...)` rules below and by its
# 16 flag-first `gh api` entries (`harness_rules.api_write_words`, the bare and the `*` form of each of 8 flags). Codex rose on
# 2026-11-08 by `aidd agree *` in each of aidd's launch forms: the command that records an Intent's agreement, which must ask.
BYTES_CAP = {"codex": 19_000, "qwen": 21_000}
# The bytes of the file each glob or regular-expression format holds, set on 2026-11-07 at what the built-in risk rules give
# today, and `budgets.within` adds the headroom. The `gh api` writes cost one small set of patterns for every endpoint
# (`harness_rules.api_write_patterns`), and the built-in actions keep no `gh api` pattern of their own. Exact patterns for
# each endpoint and each spelling of a method had grown the files to three times this size or more, and every review found a
# spelling more, so the harnesses ask before any `gh api` write instead.
# `repo.settings.change` added the four `gh repo` patterns the same day. Grok Build rose on 2026-11-08 by the 19 `Read(...)` rules
# for the files that hold secrets (R407), a rule each harness with a read tool needs. Claude Code rose the
# same day by the read rules the R407 re-reviews added (key stores and mobile config files) and by its `Read(!...)`
# carve-outs: the four `.env` templates and the 25 source-code extensions that `credentials.*` and `secrets.*` leave out.
# OpenCode rose on 2026-11-08 from 14_900, with no new pattern, because aidd supports only OpenCode v2 and later and writes
# each ask as a rule of v2's `permissions` list, three keys where v1's `permission.bash` took one, each rule on one line.
# Claude Code rose on 2026-11-08 by `aidd agree *` in each of aidd's launch forms, and its two forms for any spelling (`intent.agree`, an ask).
GLOB_BYTES_CAP = {"claude-code": 15_900, "opencode": 29_300, "grok": 13_000, "vscode": 19_900}


class WidenedPrefixBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patterns = risk.harness_patterns(risk.rule_set(None), "main")
        cls.read_paths = risk.harness_read_paths(risk.rule_set(None))

    def words_formats(self) -> list[str]:
        return sorted(fmt for fmt, f in harness_rules.FORMATS.items() if f.match == "words")

    def test_every_leading_words_format_has_a_byte_cap(self):
        self.assertEqual(self.words_formats(), sorted(BYTES_CAP), "a new leading-words format names its byte cap here")

    def test_widened_prefixes_stay_within_their_budget(self):
        for fmt in self.words_formats():
            with self.subTest(fmt=fmt):
                widened = risk.widened(fmt, self.patterns)
                self.assertTrue(
                    budgets.within(len(widened), WIDENED_CAP),
                    f"{fmt} widens {len(widened)} prefixes, cap {WIDENED_CAP}: {sorted(set(widened.values()))}. Give the new pattern a leading-words form, or raise the cap with the reason",
                )

    def test_the_rules_each_leading_words_format_writes_stay_within_their_byte_budget(self):
        for fmt in self.words_formats():
            with self.subTest(fmt=fmt), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                risk.apply_harness_rules(root, fmt, self.patterns, read_paths=self.read_paths)
                size = (root / harness_rules.FORMATS[fmt].path).stat().st_size
                self.assertTrue(budgets.within(size, BYTES_CAP[fmt]), f"{fmt}: {size} bytes, cap {BYTES_CAP[fmt]}")

    def test_every_other_format_has_a_byte_cap_too(self):
        others = sorted(fmt for fmt, f in harness_rules.FORMATS.items() if f.match != "words")
        self.assertEqual(others, sorted(GLOB_BYTES_CAP), "a new glob or regex format names its byte cap here")

    def test_the_rules_each_glob_format_writes_stay_within_their_byte_budget(self):
        for fmt, cap in GLOB_BYTES_CAP.items():
            with self.subTest(fmt=fmt), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                risk.apply_harness_rules(root, fmt, self.patterns, read_paths=self.read_paths)
                size = (root / harness_rules.FORMATS[fmt].path).stat().st_size
                self.assertTrue(
                    budgets.within(size, cap), f"{fmt}: {size} bytes, cap {cap}. Give a new pattern a smaller form, or raise the cap with the reason"
                )

    def test_the_budget_catches_a_new_widened_prefix(self):
        wider = [*self.patterns, "gh release create *notes*"]
        before = len(risk.widened("codex", self.patterns))
        self.assertEqual(len(risk.widened("codex", wider)), before + 1)
        self.assertFalse(budgets.within(WIDENED_CAP + 1, WIDENED_CAP))


if __name__ == "__main__":
    unittest.main()
