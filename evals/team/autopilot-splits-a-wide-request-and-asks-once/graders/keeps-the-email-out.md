---
type: regex
pattern: 'dana\.lee@example\.com'
flags: ''
match: not_contains
target:
  source: file
  path: .git/commits.log
---
