---
type: regex
pattern: '^merged '
flags: m
match: not_contains
target:
  source: file
  path: merge.log
---
