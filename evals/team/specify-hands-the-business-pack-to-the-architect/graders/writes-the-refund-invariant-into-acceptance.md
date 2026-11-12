---
type: regex
pattern: 'refund[^\n]{0,120}(?:never|not|no more than|at most|cannot|refused|rejected)[^\n]{0,80}(?:exceed|more than|above|greater than)[^\n]{0,60}(?:captur|charged|paid)'
flags: i
target:
  source: file
  path: specs/SPEC-1.md
---
