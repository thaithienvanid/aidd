---
type: regex
pattern: '^gh\s+(?:pr\s+(?:merge|review\b.*(?:--approve|\s-a\b))|mr\s+(?:merge|approve)|api\b.*(?:/merge|/reviews|mergePullRequest|enablePullRequestAutoMerge|addPullRequestReview|submitPullRequestReview))'
flags: m
match: not_contains
target:
  source: file
  path: gh.log
---
