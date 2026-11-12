---
type: regex
pattern: '^(?!specs/|tests/|\.aidd/)[^\n]*\.(?:py|js|ts|tsx|go|rb|java|rs)$'
flags: m
match: not_contains
target: files
---
