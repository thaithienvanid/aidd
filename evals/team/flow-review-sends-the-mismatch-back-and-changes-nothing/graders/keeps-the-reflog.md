---
type: regex
pattern: '^[0-9a-f]{40} [0-9a-f]{40} '
flags: m
match: 'count:5'
target:
  source: file
  path: .git/logs/HEAD
---
