---
description: 'A nearby request that is not about finding the cause of a failure leaves the debugging practice skill alone.'
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

This repository uses aidd. Add a unit test for this function, which works today. Cover accents and an empty string.

```python
import unicodedata


def slugify(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return "-".join(plain.lower().split())
```
