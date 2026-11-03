---
description: A fast-lane change to a user-facing surface, with no Spec, reaches the product designer, who reviews the changed screen through the fidelity pass, with proof, and approves nothing.
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
tags:
  - practice
---

We changed the toolbar of our internal admin tool on the fast lane, with no Spec. Nine size buttons became one dropdown, and three toggles moved into a "Checks" menu. The page is `admin/toolbar.html` in this repository. Before we merge, please give it a design review as our product designer.
