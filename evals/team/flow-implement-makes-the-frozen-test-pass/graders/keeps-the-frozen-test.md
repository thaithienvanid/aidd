---
type: regex
pattern: '^import unittest\n\nfrom notes import store\nfrom notes\.limit import NoteLimitReached\n\n\ndef fill\(user, count\):\n    for n in range\(count\):\n        store\.add_note\(user, f"note \{n\}"\)\n\n\nclass LimitTests\(unittest\.TestCase\):\n    def test_a_user_with_99_notes_can_add_one\(self\):\n        fill\("limit-a1", 99\)\n        store\.add_note\("limit-a1", "the hundredth"\)\n        self\.assertEqual\(store\.count_notes\("limit-a1"\), 100\)\n\n    def test_a_user_with_100_notes_is_refused_with_the_message\(self\):\n        fill\("limit-a2", 100\)\n        with self\.assertRaises\(NoteLimitReached\) as refused:\n            store\.add_note\("limit-a2", "one more"\)\n        self\.assertEqual\(str\(refused\.exception\), "You can keep at most 100 notes\."\)\n        self\.assertEqual\(store\.count_notes\("limit-a2"\), 100\)\n\n\nif __name__ == "__main__":\n    unittest\.main\(\)\n(?![\s\S])'
target:
  source: file
  path: tests/test_limit.py
---
