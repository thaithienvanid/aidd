---
type: regex
pattern: '^(?:src/login\.py|tests/test_login\.py)$'
flags: m
match: not_contains
target:
  source: file
  path: commit.log
---
