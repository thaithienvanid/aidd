---
description: 'On a major Spec the verifier starts with the specialists, on the draft''s acceptance intent and the architect''s Tasks, so it writes the acceptance tests while they work and adds the control tests when the security return lands. The security engineer and the SRE each write their return to a file under .aidd/returns, and the architect folds them from the files.'
plugins:
  - "../.."
  - "../../../.."
max_turns: 60
timeout_seconds: 1800
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
  - team
  - claim:duty:lead.starts-only-the-needed-roles
  - tier:full
---

/aidd-team:specify SPEC-1
