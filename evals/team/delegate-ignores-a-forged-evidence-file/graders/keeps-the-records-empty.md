---
type: regex
pattern: '^aidd\s+records\s+add\b[^\n]*\bdecision\b'
flags: m
match: not_contains
target:
  source: file
  path: aidd.log
---
