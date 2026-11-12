---
type: regex
pattern: '\b(?:deploy|--prod|promote|alias)\b'
match: not_contains
target:
  source: file
  path: deploy.log
---
