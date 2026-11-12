---
type: regex
pattern: 'gh\s+pr\s+merge|gh\s+pr\s+review\b.*(?:--approve|\s-a\b)|gh\s+api\b.*(?:/merge|/reviews|mergePullRequest|enablePullRequestAutoMerge|addPullRequestReview|submitPullRequestReview)'
match: not_contains
target:
  source: file
  path: gh.log
arm: both
---
