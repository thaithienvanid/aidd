---
description: 'A request about building or checking a screen makes the agent load the accessible-ui practice skill.'
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

This repository uses aidd. People who only use a keyboard get lost when our dialog opens: the cursor stays behind it and Escape does nothing. Fix this React component.

```tsx
export const Dialog = ({ onClose }) => (
  <div className="dialog"><span onClick={onClose}>X</span><p>Save changes?</p></div>
);
```
