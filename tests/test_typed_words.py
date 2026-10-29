"""A typed decision reads the same in every harness: aidd's prompt hook (typed_words.plain_typed) and aidd-mods
(plainTyped in plugins/aidd-mods/hooks/aidd.ts, whose suite holds the same cases) fold a prompt one way before they read
it. So a fullwidth word, a no-break space, or a zero-width character never makes a decision read one way here and
another way there, and an agent cannot hide a decision from the guard in them.
"""

from __future__ import annotations

import unittest

from helpers import ROOT

from aidd.workitems import typed_words

CASES = {
    "appr\u200bove SPEC-1": "approve SPEC-1",
    "\uff41pprove \uff33\uff30\uff25\uff23\uff0d\uff11": "approve SPEC-1",
    "land\u00a0it": "land it",
    "\ufeffmerge it\u2060": "merge it",
    "fix the login page": "fix the login page",
    "approve SPEC-\u202e12\u202c": "",
    "approve SPEC-1\u00b9": "",
    "approve SPEC-\u2460": "",
}


class PlainTypedTests(unittest.TestCase):
    def test_a_prompt_is_folded_one_way(self):
        for raw, plain in CASES.items():
            with self.subTest(raw=raw):
                self.assertEqual(typed_words.plain_typed(raw), plain)

    def test_the_folded_words_decide(self):
        self.assertEqual(typed_words.parse_typed("appr\u200bove SPEC-1"), ("spec", ["SPEC-1"]))
        self.assertEqual(typed_words.parse_typed("land\u2003it"), ("land", []))
        self.assertEqual(typed_words.parse_typed("\uff41pprove all"), ("all", []))
        self.assertIsNone(typed_words.parse_typed("approve\u200b the plan"))
        self.assertIsNone(typed_words.parse_typed("approve SPEC-\u202e12\u202c"))  # shows as SPEC-21: decides nothing
        self.assertIsNone(typed_words.parse_typed("decide PROP\u0131-1 go"))  # a dotless i is no letter of an id, as in the mod
        self.assertIsNone(typed_words.parse_typed("sign off PROP\u0130-1"))

    def test_the_mod_folds_the_same_way_with_the_same_cases(self):
        source = (ROOT / "plugins" / "aidd-mods" / "hooks" / "aidd.ts").read_text(encoding="utf-8")
        self.assertIn(".normalize('NFKC').replace(/\\p{Cf}/gu, '').replace(/\\p{Zs}/gu, ' ')", source)
        suite = (ROOT / "plugins" / "aidd-mods" / "hooks" / "register.test.tsx").read_text(encoding="utf-8")
        for raw, plain in CASES.items():
            if raw != plain:
                escaped = "".join(c if ord(c) < 128 else f"\\u{ord(c):04x}" for c in raw)
                self.assertIn(f"expect(plainTyped('{escaped}')).toBe('{plain}')", suite, raw)


if __name__ == "__main__":
    unittest.main()
