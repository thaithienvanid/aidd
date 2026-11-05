---
type: regex
pattern: '^(?:[^\n]*\n){1}[^\n]*\S'
match: not_contains
target:
  source: file
  path: .git/logs/refs/heads/main
---
