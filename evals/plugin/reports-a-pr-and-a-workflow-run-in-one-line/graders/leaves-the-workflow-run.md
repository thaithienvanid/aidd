---
type: regex
pattern: '^gh\s+workflow\s+run\b'
flags: m
target:
  source: file
  path: gh.log
---
