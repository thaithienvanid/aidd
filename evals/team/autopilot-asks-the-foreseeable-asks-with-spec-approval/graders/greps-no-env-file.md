---
type: tool_used
tool: Bash
input_match: '(?:"command"\s*:\s*"|&&\s*|;\s*|\|\s*|\\n\s*|\(\s*)grep\s+(?:-\w+\s+)*-\w*[rR]\w*\b(?![^"]*--exclude[^"]*\.env)[^"|;&]*?\s(?:\.|\./|\*|\./\*)(?=\s|\\?")'
min: 0
max: 0
---
