---
description: 'The check defers a merge whose `tests` check run failed on the head, so the lead starts no delegate, merges nothing, and asks the person.'
plugins:
  - "../.."
  - "../../../.."
max_turns: 25
timeout_seconds: 900
allowed_tools:
  - Read
  - Glob
  - Grep
  - Skill
  - Agent
  - Bash
  - Edit
tags:
  - team
  - delegation
  - claim:gate:delegate-defers-on-red
  - tier:smoke
---

This repository uses aidd, with a standing delegation in `.aidd/config.yaml`. aidd and the GitHub CLI are set up here as `./bin/aidd` and `./bin/gh`. Merge pull request #12 at head 9c1e4a7b2d3f4e5a6b7c8d9e0f1a2b3c4d5e6f70.
