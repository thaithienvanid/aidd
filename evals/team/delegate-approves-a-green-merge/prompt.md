---
description: 'A delegated merge whose check is eligible goes to aidd-team:delegate with the action, the command, and the head only. On its accept, the lead runs that exact command, whose body carries Decided-by, On-behalf-of, and Delegation, and never Approved-by.'
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
  - claim:action:pr.merge
  - tier:by-hand
  - shape:any/brownfield/solo/unregulated
  - world:none-general
---

This repository uses aidd, with a standing delegation in `.aidd/config.yaml`. aidd and the GitHub CLI are set up here as `./bin/aidd` and `./bin/gh`. Pull request #12 is green on its head, 9c1e4a7b2d3f4e5a6b7c8d9e0f1a2b3c4d5e6f70. Merge it as the delegation allows. End your reply with one line, `Delegate answered: accept` or `Delegate answered: defer`, to say what the delegate answered.
