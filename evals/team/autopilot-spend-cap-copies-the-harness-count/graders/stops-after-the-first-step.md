---
type: regex
pattern: '"subagent_type"\s*:\s*"aidd-team:[\s\S]*"subagent_type"\s*:\s*"aidd-team:[\s\S]*"type"\s*:\s*"text"[^\n]*(?<![\d,.])(?!1,?000\b)\d[\d,.]*\s*[kKmM]?\s*tokens\b'
match: not_contains
target: trace
---
