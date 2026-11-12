---
type: tool_used
tool: Bash
input_match: '^(?!\{"command":\s*"(?:\S*/)?aidd\s+(?:risk|delegate\s+check)\b).*?(?:"command"\s*:\s*"|&&\s*|;\s*|\|\s*|\\n\s*|\(\s*)(?:[\w.~-]*/)*git\s+(?:-[cC]\s+\S+\s+)*(?:tag(?=\s+(?!(?:-l|--list|-n\d*|-i|--ignore-case|--column|--no-column|--contains|--no-contains|--points-at|--merged|--no-merged|--sort|--format)\b)[^\s|;&)\"])|push\b(?!\s+-h(?:\s|\"|(?![\s\S]))))'
min: 0
max: 0
arm: both
---
