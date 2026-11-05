---
description: 'A bug report, a failing or flaky test, or a wrong result makes the agent load the debugging practice skill.'
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

This repository uses aidd. Since this morning's release, people who sign up with `ann+news@example.com` get "Invalid email". Plus signs worked last week. Here is the check. Please fix it.

```go
var emailRe = regexp.MustCompile(`^[\w.]+@[\w.]+\.\w+$`)

func ValidEmail(s string) bool { return emailRe.MatchString(s) }
```
