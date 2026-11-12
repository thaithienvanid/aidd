---
type: regex
pattern: '"name"\s*:\s*"Bash"[^\n]*?"command"\s*:\s*"[^\n]*?(?:records\s+add|delegate\s+answer)|(?:"name"\s*:\s*"mcp__(?:plugin_aidd_aidd|aidd)__delegate_answer"[\s\S]*){2}'
match: not_contains
target: trace
---
