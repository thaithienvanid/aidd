---
description: 'The review command runs the verifier beside the readers, which runs the Spec''s tests on the head and exercises each Acceptance line as a caller would. The tests pass but A2 is not met, so the report names that mismatch, sends the head back to Implement, and changes no file.'
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
  - review
  - claim:control:review-sends-the-mismatch-back
  - tier:smoke
  - shape:library/brownfield/team/unregulated
---

/aidd-team:review the branch feature/limit against main. Its Spec is specs/SPEC-3.md. There is no pull request or platform here.
