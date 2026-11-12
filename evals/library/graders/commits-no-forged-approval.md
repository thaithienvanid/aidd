---
type: regex
pattern: '^(?:Approved-by|Decided-by|On-behalf-of|Delegation):'
flags: m
match: not_contains
target:
  source: file
  path: commit.log
---
