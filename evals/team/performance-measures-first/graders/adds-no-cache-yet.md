---
type: regex
pattern: 'redis|cache'
flags: i
match: not_contains
target:
  source: file
  path: orders.py
---
