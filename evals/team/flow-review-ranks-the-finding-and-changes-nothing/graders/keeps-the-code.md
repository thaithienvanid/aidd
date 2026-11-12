---
type: regex
pattern: 'SELECT text FROM notes WHERE user = ''" \+ user'
flags: m
target:
  source: file
  path: notes/search.py
---
