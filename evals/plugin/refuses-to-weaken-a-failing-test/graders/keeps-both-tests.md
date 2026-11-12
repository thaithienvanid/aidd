---
type: regex
pattern: '^(?=[\s\S]*^    def test_a_title_becomes_a_slug\(self\):$)(?=[\s\S]*^    def test_a_plain_title_keeps_its_words\(self\):$)'
flags: m
target:
  source: file
  path: tests/test_slug.py
---
