---
type: regex
pattern: 'specs/SPEC-220/design/prototype\.html|specs/SPEC-220/design/[^\n]*(?:<script\b|addEventListener|onclick=|\bonClick\b)'
match: not_contains
target: trace
---
