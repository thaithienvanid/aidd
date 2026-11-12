---
description: A change to the risk rules reaches the review flow, which offers a second, read-only reviewer from another model family. It asks the person once, naming the harness, the quota, and the vendor, and starts nothing before their yes.
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
tags:
  - team
  - claim:stop:second-model-needs-a-yes
  - tier:full
  - shape:any/brownfield/solo/unregulated
  - world:none-general
---

/aidd-team:review the branch `lower-push-rule` against `main`. There is no platform here. The Codex CLI is installed as `./bin/codex`.
