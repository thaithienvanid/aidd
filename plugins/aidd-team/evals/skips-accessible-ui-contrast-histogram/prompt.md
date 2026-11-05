---
description: 'A nearby request that is not about building or checking a screen leaves the accessible-ui practice skill alone.'
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
  - accessible-ui
  - claim:trigger:accessible-ui
  - tier:description-change
---

This repository uses aidd. Our contrast histogram code, `equalize(image, clip=2.0)`, returns a washed-out result on dark images. Explain what the clip value does.
