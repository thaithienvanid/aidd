---
type: regex
pattern: '^approved_by:'
flags: m
match: not_contains
target:
  source: file
  path: specs/SPEC-4.md
---
