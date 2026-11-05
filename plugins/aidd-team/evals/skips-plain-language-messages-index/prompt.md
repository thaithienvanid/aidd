---
description: 'A nearby request that is not about writing prose a person reads leaves the plain-language practice skill alone.'
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
  - plain-language
  - claim:trigger:plain-language
  - tier:description-change
---

This repository uses aidd. Our messages table has a `body` column of type TEXT. Add an index on `(user_id, created_at)` with a migration.
