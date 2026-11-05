---
description: 'Under solo with no remote, an eligible local merge goes to aidd-team:delegate. On its accept, the lead runs the exact `git merge --no-ff` command the check covered, whose message carries the three trailers and never Approved-by.'
plugins:
  - "../../../plugins/aidd-team"
  - "../../.."
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
  - claim:action:git.merge
  - tier:by-hand
  - shape:any/brownfield/solo/unregulated
---

This repository uses aidd, with a standing delegation in `.aidd/config.yaml`. aidd and the GitHub CLI are set up here as `./bin/aidd` and `./bin/gh`. Merge feature/cart into main at 9c1e4a7b2d3f4e5a6b7c8d9e0f1a2b3c4d5e6f70. There is no remote here. End your reply with one line, `Delegate answered: accept` or `Delegate answered: defer`, to say what the delegate answered.
