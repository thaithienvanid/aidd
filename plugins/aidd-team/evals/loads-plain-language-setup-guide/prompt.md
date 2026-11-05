---
description: 'A request about writing prose a person reads makes the agent load the plain-language practice skill.'
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

This repository uses aidd. Rewrite this paragraph of our onboarding guide so a new hire can follow it.

> Prior to the instantiation of the local environment, the operator must ensure that the requisite dependencies have been provisioned in accordance with the manifest.
