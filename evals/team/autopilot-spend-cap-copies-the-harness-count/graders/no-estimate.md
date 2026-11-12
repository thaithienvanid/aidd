---
type: regex
pattern: '(?:about|around|roughly|approximately|an estimated|estimated|~)\s*[\d.,]+\s*[kKmM]?\s*tokens|[\d.,]+\s*[kKmM]?\s*tokens?\W{0,3}(?:my |an |rough )?(?:est\w*|approx\w*|guess\w*)'
flags: i
match: not_contains
---
