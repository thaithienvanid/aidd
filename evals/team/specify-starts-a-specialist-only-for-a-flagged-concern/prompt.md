---
description: 'A normal draft Spec whose import fetches any web address the user pastes holds one real security concern, and no personal data or compliance target. The architect writes the Spec with a Concerns section, the security engineer starts for the flagged concern, and the compliance analyst does not.'
plugins:
  - "../../../plugins/aidd-team"
  - "../../../plugins/aidd-packs"
  - "../../.."
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
  - shape:library/brownfield/team/unregulated
  - world:python-notes
---

/aidd-team:specify SPEC-1
