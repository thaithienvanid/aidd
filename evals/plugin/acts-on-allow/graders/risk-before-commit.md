---
type: regex
pattern: '"id"\s*:\s*"([^"\\]+)"\s*,\s*(?:"name"\s*:\s*"Bash"\s*,\s*"input"\s*:\s*\{\s*"command"\s*:\s*"(?:cd\s[^"&;|]*(?:&&|;)\s*)?(?:[A-Za-z_]\w*=\S*\s+)*(?:(?:ba|z)?sh\s+|python3?\s+-m\s+)?(?:(?:\\")?[\w.~${}/-]*/)?aidd(?:\\")?\s+risk\b(?!\s+(?:--help|-h)\b)|"name"\s*:\s*"mcp__(?:plugin_aidd_aidd|aidd)__risk")(?![\s\S]*"tool_use_id"\s*:\s*"\1"[^\n]*"is_error"\s*:\s*true)(?![\s\S]*"is_error"\s*:\s*true[^\n]*"tool_use_id"\s*:\s*"\1")[^\n]*\n[\s\S]*?"name"\s*:\s*"Bash"\s*,\s*"input"\s*:\s*\{\s*"command"\s*:\s*"(?:(?:[^"\\]|\\.)*?(?:&&|;|\\n)\s*)?(?:[A-Za-z_]\w*=\S*\s+)*(?:[\w.~-]*/)*git\s+(?:-[cC]\s+\S+\s+)*commit\b(?!-tree)'
target: trace
---
