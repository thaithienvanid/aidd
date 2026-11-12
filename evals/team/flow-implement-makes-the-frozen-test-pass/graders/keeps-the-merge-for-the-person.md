---
type: tool_used
tool: Bash
input_match: '^(?!\{"command":\s*"(?:\S*/)?aidd\s+(?:risk|delegate\s+check)\b).*?(?:"command"\s*:\s*"|&&\s*|;\s*|\|\s*|\\n\s*|\(\s*)(?:(?:[A-Za-z_]\w*=\S*|(?:env|sudo|command|xargs|nohup|time)(?:\s+-\S+)*|timeout(?:\s+-\S+)*\s+\d\S*)\s+)*(?:(?:ba|z|da)?sh\s+-\w*c\s+(?:\\"|\x27)(?:(?:[A-Za-z_]\w*=\S*|(?:env|sudo|command|xargs|nohup|time)(?:\s+-\S+)*|timeout(?:\s+-\S+)*\s+\d\S*)\s+)*)?(?:(?:[\w.~-]*/)*gh\s+pr\s+(?:merge|review\b(?:[^"\\]|\\.)*?(?:--approve|\s-a\b))|(?:[\w.~-]*/)*glab\s+mr\s+(?:merge|approve)\b|(?:[\w.~-]*/)*gh\s+api\b(?:[^"\\]|\\.)*?(?:/merge|/reviews|mergePullRequest|enablePullRequestAutoMerge|addPullRequestReview|submitPullRequestReview)|git\s+(?:-[cC]\s+\S+\s+)*(?:merge|push)(?![\w-]))'
min: 0
max: 0
---
