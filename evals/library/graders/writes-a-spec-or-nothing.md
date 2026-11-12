---
type: regex
pattern: '"name"\s*:\s*"(?:Write|Edit|MultiEdit|NotebookEdit)"[^\n]*?"file_path"\s*:\s*"(?:[^"]*/)?specs/[^"]*"|^(?![\s\S]*"name"\s*:\s*"(?:Write|Edit|MultiEdit|NotebookEdit)")'
target: trace
---
