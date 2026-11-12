---
type: regex
pattern: 'average_length\([^\n]*\)\s*==\s*5(?:\.0+)?\b|assert\w*\(\s*average_length\([^\n]*\),\s*5(?:\.0+)?\s*\)'
flags: m
target:
  source: file
  path: tests/test_summary.py
---
