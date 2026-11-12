---
type: regex
pattern: 'Ran \d+ tests? in [\d.]+s\\n\\nOK(?![\s\S]*"name"\s*:\s*"(?:Edit|Write|MultiEdit)")|\d+ passed(?![^\n"]*failed)(?![\s\S]*"name"\s*:\s*"(?:Edit|Write|MultiEdit)")'
target: trace
---
