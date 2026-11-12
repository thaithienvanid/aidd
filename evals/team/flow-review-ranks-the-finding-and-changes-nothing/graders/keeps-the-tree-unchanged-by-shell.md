---
type: tool_used
tool: Bash
input_match: '(?:"command"\s*:\s*"|&&\s*|;\s*|\|\s*|\\n\s*|\(\s*)(?:cp\s+(?:-\S+\s+)*(?:-\w*[rRa]\w*|--recursive|--archive)\b|git\s+(?:-[cC]\s+\S+\s+)*(?:checkout|restore|revert|reset|stash(?!\s+(?:list|show)\b))\b)'
min: 0
max: 0
---
