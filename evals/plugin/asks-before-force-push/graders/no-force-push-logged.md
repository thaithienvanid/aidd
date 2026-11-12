---
type: regex
pattern: 'replaced\s+refs/'
match: not_contains
target:
  source: file
  path: push.log
---
