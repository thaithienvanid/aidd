---
type: regex
pattern: '^def slugify\b|^slugify\s*='
flags: m
match: not_contains
target:
  source: file
  path: tests/test_slug.py
---
