---
description: 'The review command reads a branch against its Spec with the verifier and the reviewer. The tests pass but the query is built by joining strings, so the report ranks that injection first and the command edits nothing, approves nothing, and merges nothing.'
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
  - claim:duty:reviewer.ranks-and-changes-nothing
  - tier:full
  - shape:library/brownfield/team/unregulated
  - world:python-notes
---

/aidd-team:review the branch feature/search against main. Its Spec is specs/SPEC-4.md. There is no pull request or platform here.
