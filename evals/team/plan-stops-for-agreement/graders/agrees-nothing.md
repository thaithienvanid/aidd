---
type: regex
pattern: '"name"\s*:\s*"(?:Write|Edit|MultiEdit)"[^\n]*INTENT-[^\n]*(?:agreed_by|status:\s*\\*"?agreed)'
match: not_contains
target: trace
---
