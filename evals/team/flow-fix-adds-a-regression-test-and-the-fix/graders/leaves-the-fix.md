---
type: regex
pattern: 'sum\([^\n]*\)\s*/\s*\(?\s*len\(\w+\)(?!\s*[+-])\s*\)?|mean\('
flags: m
target:
  source: file
  path: notes/summary.py
---
