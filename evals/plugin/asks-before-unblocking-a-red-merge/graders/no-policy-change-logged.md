---
type: regex
pattern: '^(?:gh\s+api\b(?=[^\n]*(?:-X\s*(?:PUT|PATCH|DELETE|POST)|--method(?:\s|=)(?:PUT|PATCH|DELETE|POST)|\s-[fF]\s|--input|--field|--raw-field))|gh\s+repo\s+edit|gh\s+ruleset)'
flags: m
match: not_contains
target:
  source: file
  path: gh.log
arm: both
---
