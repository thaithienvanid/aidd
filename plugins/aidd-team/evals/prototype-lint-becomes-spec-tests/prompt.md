---
description: The prototype rules become deterministic Spec test commands that catch every seeded violation, with command vectors the verifier can freeze.
plugins:
  - "../.."
  - "../../../.."
max_turns: 30
timeout_seconds: 900
allowed_tools:
  - Read
  - Glob
  - Grep
  - Skill
  - Bash
  - Write
tags:
  - practice
---

Our prototype for SPEC-220 is the one file `specs/SPEC-220/design/prototype.html`, and its `<style id="tokens">` block holds the color roles generated from `design/tokens.json`. Before Spec approval I want the prototype rules to be Spec tests, so a violation turns the run red. Here is one screen of it:

```html
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter">
<style>
  .card { background: var(--color-surface); color: #1a1a1a; padding: var(--space-3); }
  .total { color: rgb(200, 30, 30); }
</style>
<div class="card">
  <h2>Lorem ipsum dolor</h2>
  <p>Your Name owes 12.50</p>
  <div class="icon-btn" onclick="split()">✂️</div>
  <img src="https://images.example.com/avatar.png">
  <!-- TODO: real copy -->
</div>
```

Write the checks as Spec test commands.
