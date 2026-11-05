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

This repository uses aidd. Move the `Label` component from `ui/label.py` to `ui/forms/label.py` and fix the import in this file.

```python
from ui.label import Label
```
