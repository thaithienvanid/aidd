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

This repository uses aidd. Validate the form data posted to `/signup` in this handler. The email must contain an @, and the password must have 8 characters or more.

```python
def signup(form):
    return create_user(form["email"], form["password"])
```
