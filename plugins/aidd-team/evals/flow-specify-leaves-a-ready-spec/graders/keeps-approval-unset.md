---
type: regex
pattern: '^(?:approved_by|approved_at):'
flags: m
target:
  source: file
  path: specs/SPEC-1.md
match: not_contains
---
