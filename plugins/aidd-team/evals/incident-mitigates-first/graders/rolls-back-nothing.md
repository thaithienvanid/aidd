---
type: tool_used
tool: Bash
input_match: '^(?!\{"command":\s*"(?:\S*/)?aidd\s+(?:risk|delegate\s+check)\b).*?(?:"command"\s*:\s*"|&&\s*|;\s*|\|\s*|\\n\s*|\(\s*)git\s+(?:-[cC]\s+\S+\s+)*(?:revert|reset|push|checkout)(?![\w-])'
min: 0
max: 0
---
