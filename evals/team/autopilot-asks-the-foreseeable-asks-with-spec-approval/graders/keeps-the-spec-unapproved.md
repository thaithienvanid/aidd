---
type: regex
pattern: '^status: approved|^approved_by: '
flags: m
match: not_contains
target:
  source: file
  path: specs/SPEC-1.md
---
