---
description: 'A nearby request that adds no call across a process boundary leaves the resilience practice skill alone.'
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
  - resilience
  - claim:trigger:resilience
  - tier:description-change
---

This repository uses aidd. Our `customers` table has duplicates: two rows with the same email. Write the SQL that lists them and the unique index that stops new ones. Then say how to remove the extra rows safely.
