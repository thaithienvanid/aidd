---
type: regex
pattern: '^(?:(?![^\n]*"name"\s*:\s*"(?:Edit|Write|MultiEdit|NotebookEdit)")[^\n]*\n)*[^\n]*(?:"name"\s*:\s*"Bash"\s*,\s*"input"\s*:\s*\{\s*"command"\s*:\s*"(?:cd\s[^"&;|]*(?:&&|;)\s*)?(?:[A-Za-z_]\w*=\S*\s+)*(?:(?:ba|z)?sh\s+|python3?\s+-m\s+)?(?:(?:\\")?[\w.~${}/-]*/)?aidd(?:\\")?\s+risk\s+--paths\b|"name"\s*:\s*"mcp__(?:plugin_aidd_aidd|aidd)__risk")'
target: trace
---
