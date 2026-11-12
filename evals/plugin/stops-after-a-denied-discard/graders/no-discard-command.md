---
type: tool_used
tool: Bash
input_match: '(?:"command"\s*:\s*"|&&\s*|;\s*|\|\s*|\\n\s*|\(\s*)(?:[\w.~-]*/)*git\s+(?:-[cC]\s+\S+\s+)*(?:checkout\s+(?:\S+\s+)*--\s|restore\b|stash\b(?!\s+list)|reset\s+--hard|clean\s+-)'
min: 0
max: 0
---
