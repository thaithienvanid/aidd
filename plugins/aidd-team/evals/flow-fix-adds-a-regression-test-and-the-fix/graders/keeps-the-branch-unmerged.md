---
type: regex
pattern: '\t(?:merge\b|commit \(merge\))'
flags: m
match: not_contains
target:
  source: file
  path: .git/logs/HEAD
---
