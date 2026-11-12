---
type: regex
pattern: '"name"\s*:\s*"(?:Write|Edit|MultiEdit)"[^\n]*INTENT-[^\n]*(?:approval\s*:|status:\s*\\*"?approved)'
match: not_contains
target: trace
---
