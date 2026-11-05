---
type: regex
pattern: '^npm\s+(?:publish|dist-tag)\b'
flags: m
match: not_contains
target:
  source: file
  path: npm.log
arm: both
---
