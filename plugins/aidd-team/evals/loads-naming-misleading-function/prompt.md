---
description: 'A request about choosing or improving a name makes the agent load the naming practice skill.'
plugins:
  - "../.."
  - "../../../.."
max_turns: 6
timeout_seconds: 300
allowed_tools:
  - Read
  - Glob
  - Grep
  - Skill
tags:
  - trigger
  - naming
  - claim:trigger:naming
  - tier:description-change
---

This repository uses aidd. A teammate says `handle_data` in our billing area is misleading. It turns invoice lines into records ready for tax filing. Suggest a better one.
