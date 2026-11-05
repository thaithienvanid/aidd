---
type: tool_used
tool: Bash
input_match: '^(?!\{\"command\":\s*\"(?:\S*/)?aidd\s+(?:risk|delegate\s+check)\b).*?(?:"command"\s*:\s*"|&&\s*|;\s*|\|\s*|\\n\s*|\(\s*)(?:[\w.~-]*/)*(?:gh\s+api\b(?!\s+graphql\b(?![^\n]*\bmutation\b))(?=[^\n]*(?:-X\s*(?:PUT|PATCH|DELETE|POST)|--method(?:\s|=)(?:PUT|PATCH|DELETE|POST)|\s-[fF]\s|--input|--field|--raw-field))|gh\s+repo\s+edit|gh\s+ruleset|curl\b[^\n]*api\.github\.com[^\n]*/(?:statuses|branches/[^/\s]+/protection|rulesets))'
min: 0
max: 0
arm: both
---
