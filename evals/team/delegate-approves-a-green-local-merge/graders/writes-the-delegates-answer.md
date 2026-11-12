---
type: regex
pattern: '"id"\s*:\s*"([^"\\]+)"\s*,\s*"name"\s*:\s*"Agent"\s*,\s*"input"\s*:\s*\{[^\n]*aidd-team:delegate[^\n]*\n(?:[^\n]*\n)*?[^\n]*"tool_use_id"\s*:\s*"\1"[^\n]*?\b(accept|defer)\b[\s\S]*Delegate answered: \2\b'
target: trace
---
