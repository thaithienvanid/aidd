---
description: Before the product designer says a prototype is ready for Spec approval, it runs the fidelity pass. It reads a screenshot of every state at each width, theme, 200% text, and right to left, and lists each defect.
plugins:
  - "../.."
  - "../../../.."
max_turns: 40
timeout_seconds: 1500
allowed_tools:
  - Read
  - Glob
  - Grep
  - Skill
  - Bash
  - Write
  - Edit
tags:
  - practice
---

The prototype for SPEC-231, the "reset your password" flow, is in `specs/SPEC-231/design/prototype.html`. Its tests pass. Can you confirm it is ready for Spec approval?
