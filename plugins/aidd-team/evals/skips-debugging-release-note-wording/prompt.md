---
description: 'A nearby request that is not about finding the cause of a failure leaves the debugging practice skill alone.'
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
  - debugging
  - claim:trigger:debugging
  - tier:description-change
---

This repository uses aidd. Rewrite this release note line in plain words for customers: "Fixed a bug where the export broke on empty orders."
