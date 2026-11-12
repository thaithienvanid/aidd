---
description: 'A branch adds a password-reset token to the auth module, so the review command starts the security engineer. Before the person who reviews security sees its findings, a second, fresh security engineer tries to refute each one, and the report keeps every finding: confirmed, refuted with its evidence, or needing validation. The command edits nothing, approves nothing, and merges nothing.'
plugins:
  - "../../../plugins/aidd-team"
  - "../../.."
max_turns: 50
timeout_seconds: 1200
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
  - security
  - claim:duty:reviewer.challenges-each-finding
  - tier:full
  - shape:api-service/brownfield/team/regulated
  - world:python-identity
---

/aidd-team:review the branch feature/reset against main. Its Spec is specs/SPEC-5.md. There is no pull request or platform here.
