---
type: regex
pattern: '^preview:'
flags: m
match: not_contains
target:
  source: file
  path: '.aidd/config.yaml'
---
