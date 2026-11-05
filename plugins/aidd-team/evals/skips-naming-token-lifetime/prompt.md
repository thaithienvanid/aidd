---
description: 'A nearby request that is not about choosing or improving a name leaves the naming practice skill alone.'
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
  - naming
  - claim:trigger:naming
  - tier:description-change
---

This repository uses aidd. The session token expires after 15 minutes. Change the lifetime to 30 minutes in this snippet.

```python
TOKEN_LIFETIME_MINUTES = 15
```
