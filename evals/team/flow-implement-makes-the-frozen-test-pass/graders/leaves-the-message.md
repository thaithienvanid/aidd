---
type: regex
pattern: 'You can keep at most (?:100\b|\{[^}\n]+\}|%[ds]|\{\}|"\s*\+)'
flags: m
target:
  source: file
  path: notes/limit.py
---
