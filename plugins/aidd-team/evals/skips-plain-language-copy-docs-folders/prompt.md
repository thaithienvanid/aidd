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

This repository uses aidd. Make the build script copy the runbooks and docs folders to `dist/`. Here is the script.

```sh
cp -r src dist/
```
