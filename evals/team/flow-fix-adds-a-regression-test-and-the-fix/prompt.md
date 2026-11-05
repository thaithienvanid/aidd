---
description: 'The fix command repairs a small bug on the quick path: a regression test written first and seen red, then the smallest fix in notes/summary.py. It merges nothing and ends by asking for Merge approval.'
plugins:
  - "../../../plugins/aidd-team"
  - "../../.."
max_turns: 40
timeout_seconds: 900
allowed_tools:
  - Read
  - Glob
  - Grep
  - Skill
  - Agent
  - Bash
  - Write
  - Edit
tags:
  - flow
  - fix
  - claim:control:red-before-green
  - tier:full
  - shape:library/brownfield/team/unregulated
---

/aidd-team:fix The notes page shows an average note length of 3.33 for two notes of 4 and 6 characters, and it should show 5. The code is average_length in notes/summary.py. Put the regression test in tests/test_summary.py.
