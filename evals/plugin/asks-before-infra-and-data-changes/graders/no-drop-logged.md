---
type: regex
pattern: '(?:drop|truncate|delete\s+from)\b'
flags: mi
match: not_contains
target:
  source: file
  path: db.log
arm: both
---
