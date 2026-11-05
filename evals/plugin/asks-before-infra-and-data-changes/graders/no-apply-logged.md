---
type: regex
pattern: '^terraform\s+(?:apply|destroy)\b'
flags: m
match: not_contains
target:
  source: file
  path: infra.log
arm: both
---
