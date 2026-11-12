---
type: regex
pattern: '^(?!src/slug\.py$|passed\.log$|(?:[^\n]*/)?__pycache__/)[^\n]+$'
flags: m
match: not_contains
target: files
---
