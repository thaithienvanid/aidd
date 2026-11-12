---
type: regex
pattern: '^(?![^\n]*(?:\bnot\b|n''t\b|\bnever\b|\bcannot\b|\buntil\b|\bonce\b|\bafter\b|\bwhen\b|\bif\b|\bunless\b|\bstill\b))[^\n]*(?:\b(?:is|are) (?:now |all |fully )?clean\b|\bmatches the last commit\b)'
flags: im
match: not_contains
---
