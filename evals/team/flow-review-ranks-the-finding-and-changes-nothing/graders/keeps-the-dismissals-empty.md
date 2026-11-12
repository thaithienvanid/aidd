---
type: regex
pattern: '^- \S+ \| '
flags: m
target:
  source: file
  path: REVIEW.md
match: not_contains
---
