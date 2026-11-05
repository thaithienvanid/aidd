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

This repository uses aidd. Find the line that breaks the YAML in this front matter of one of our specs.

```yaml
id: notes-1
title: Notes: all
```
