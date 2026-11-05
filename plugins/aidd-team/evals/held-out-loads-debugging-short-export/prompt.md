---
description: 'A held-out paraphrase of a debugging request, scored apart. No description is tuned on it.'
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
  - held-out
  - debugging
  - claim:trigger:debugging
  - tier:held-out
---

This repository uses aidd. Since Tuesday, exported CSVs have one row fewer than the database holds. Here is the export code.

```python
def export(rows):
    return "\n".join(",".join(map(str, r)) for r in rows[:-1])
```
