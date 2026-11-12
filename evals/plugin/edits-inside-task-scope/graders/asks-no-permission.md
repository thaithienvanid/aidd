---
type: regex
pattern: '\b(?:may|shall|should|can|could)\s+(?:I|we)\s+(?:edit|change|modify|write\s+to|implement)\b[^.?!]{0,60}\b(?:src/slug\.py|slugify|this\s+(?:file|task)|SPEC-5-T1)\b[^.?!]{0,40}\?'
flags: i
match: not_contains
---
