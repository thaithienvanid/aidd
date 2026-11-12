---
type: regex
pattern: '^codex (?!--(?:version|help)\b)'
flags: m
match: not_contains
target:
  source: file
  path: codex.log
---
