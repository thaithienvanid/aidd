---
type: regex
pattern: '^(?!specs/|\.aidd/)[^\n]+\.(?:py|js|ts|tsx|jsx|go|rb|java|rs)$'
flags: m
match: not_contains
target: files
---
