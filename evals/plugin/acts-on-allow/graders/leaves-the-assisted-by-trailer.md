---
type: regex
pattern: '^Assisted-by: \S+/\S+'
flags: m
target:
  source: file
  path: commit.log
---
