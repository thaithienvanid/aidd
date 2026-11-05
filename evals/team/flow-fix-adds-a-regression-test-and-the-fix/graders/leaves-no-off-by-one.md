---
type: regex
pattern: 'len\((?:lengths|notes)\)\s*[+-]\s*1'
flags: m
target:
  source: file
  path: notes/summary.py
match: not_contains
---
