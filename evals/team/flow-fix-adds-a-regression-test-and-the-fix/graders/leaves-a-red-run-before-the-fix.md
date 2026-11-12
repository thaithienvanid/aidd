---
type: regex
pattern: '"command"\s*:\s*"[^\n]*(?:pytest|unittest|test_\w+\.py)[^\n]*\n(?:[^\n]*\n)*?[^\n]*"tool_result"[^\n]*(?:FAILED|AssertionError|failures=\d)[\s\S]*?(?:"name"\s*:\s*"(?:Edit|Write|MultiEdit)"[^\n]*(?<!\w)notes/summary\.py|"command"\s*:\s*"[^\n]*(?:sed\s+-i|>\s*\S*notes/summary\.py|python3?\s+-)[^\n]*(?<!\w)notes/summary\.py)'
target: trace
---
