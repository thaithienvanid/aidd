---
type: regex
pattern: '^(?=[\s\S]*^status: approved$)(?=[\s\S]*^approved_by: "@org\/leads"$)(?=[\s\S]*^approved_at: "2026-11-01T10:00:00Z"$)'
flags: m
target:
  source: file
  path: specs/SPEC-2.md
---
