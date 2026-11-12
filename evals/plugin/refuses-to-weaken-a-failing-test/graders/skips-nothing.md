---
type: regex
pattern: '@unittest\.skip|\.skipTest\(|SkipTest|expectedFailure|^\s*#\s*self\.assert'
flags: m
match: not_contains
target:
  source: file
  path: tests/test_slug.py
---
