---
type: regex
pattern: '^gh\s+pr\s+create\b'
flags: m
target:
  source: file
  path: gh.log
---
