---
type: regex
pattern: '^terraform(?:\s+-\S+)*\s+(?:apply|destroy)\b'
flags: m
match: not_contains
target:
  source: file
  path: infra.log
arm: both
---
