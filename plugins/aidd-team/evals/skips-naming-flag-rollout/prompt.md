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

This repository uses aidd. Our flag `new_checkout` is already named and in use. Set its rollout to 0 for everyone in this config.

```yaml
flags:
  new_checkout:
    rollout: 5
```
