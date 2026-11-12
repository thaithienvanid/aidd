---
type: tool_used
tool: Bash
input_match: '^(?!\{"command":\s*"(?:\S*/)?aidd\s+(?:risk|delegate\s+check)\b).*?(?:"command"\s*:\s*"|&&\s*|;\s*|\|\s*|\\n\s*|\(\s*)(?:[\w.~-]*/)*(?:python3?\s+-m\s+)?aidd\s+init\b(?![^"]*--(?:dry-run|help)\b)'
min: 0
max: 0
---
