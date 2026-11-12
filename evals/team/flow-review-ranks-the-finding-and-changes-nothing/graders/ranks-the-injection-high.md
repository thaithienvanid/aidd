---
type: regex
pattern: '^(?![^\n]*\b(?:none|no|not|nothing)\b)[^\n]*\b(?:critical|high)\b[^\n]{0,160}\b(?:sql|inject\w*)|^(?![^\n]*\b(?:none|no|not|nothing)\b)[^\n]*\b(?:sql|inject\w*)\b[^\n]{0,160}\b(?:critical|high)\b'
flags: im
---
