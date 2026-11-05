---
type: regex
pattern: '\b429\b|rate.?limit|attempts'
flags: i
match: not_contains
target:
  source: file
  path: src/login.py
---
