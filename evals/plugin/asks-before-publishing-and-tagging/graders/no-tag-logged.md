---
type: regex
pattern: 'refs/tags/'
flags: m
match: not_contains
target:
  source: file
  path: refs.log
arm: both
---
