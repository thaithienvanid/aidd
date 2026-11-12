---
description: 'Onboarding a service whose auth code sits past the dry run''s depth starts the security engineer anyway, because the repository holds source code, beside the architect, and writes nothing.'
plugins:
  - "../../../plugins/aidd-team"
  - "../../.."
max_turns: 40
timeout_seconds: 1500
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
  - claim:duty:lead.onboards-with-the-security-engineer
  - tier:full
  - shape:api-service/brownfield/solo/unregulated
  - world:python-identity
---

/aidd-team:onboard We will add single sign-on here next.
