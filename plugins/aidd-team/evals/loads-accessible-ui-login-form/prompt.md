---
description: 'A request about building or checking a screen makes the agent load the accessible-ui practice skill.'
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

This repository uses aidd. Build a sign-in page in SwiftUI with an email box, a password box, and a submit button.
