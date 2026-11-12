---
type: regex
pattern: '\S'
flags: m
match: not_contains
target:
  source: file
  path: push.log
arm: both
---
