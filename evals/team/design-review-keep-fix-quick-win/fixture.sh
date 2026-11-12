#!/usr/bin/env bash
set -euo pipefail
# The files the review notes name: SPEC-220 with its approved prototype, the built stylesheet whose line 18 holds a raw
# color, and four screenshots in review/SPEC-220/ (one-pixel stand-ins). The files are ours and are written only inside
# the case's workspace.
mkdir -p .aidd specs/SPEC-220/design src/checkout review/SPEC-220
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: team

owners:
  approvers: ["@org/leads"]
YAML
cat > specs/SPEC-220.md <<'MD'
---
type: spec
id: SPEC-220
title: Split the bill at checkout
route: normal
status: approved
change_type: feat
approved_by: "@org/leads"
approved_at: "2026-11-01T10:00:00Z"
rollback: Revert the change.
risk:
  summary: A customer can split a bill between up to four people.
  dimensions: []
  irreversible: false
tasks:
  - id: SPEC-220-T1
    title: Split the total at checkout
    scope: ["src/checkout/"]
    assignee: "role:developer"
tests:
  files: ["tests/test_split.py"]
  commands:
    - name: acceptance
      command: ["python3", "-m", "unittest", "tests.test_split"]
      new_behavior: true
      covers: [A1]
---

## Request

After the cart, a customer splits the total between up to four people.

## Acceptance

- A1: Given a total, when a customer splits it between four people, then each person sees a share.

## Design

The approved prototype is `specs/SPEC-220/design/prototype.html`. Colors come from the tokens, such as `color.focus` and `color.danger`.
MD
cat > specs/SPEC-220/design/prototype.html <<'HTML'
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Split the bill</title>
<style id="tokens">
  :root { --color-danger: #c62828; --color-focus: #1d4ed8; --color-surface: #ffffff; }
</style>
<style>
  button:focus-visible { outline: 2px solid var(--color-focus); }
  .total { color: var(--color-danger); }
</style>
</head>
<body>
<section data-screen="split">
  <p class="total">12.50 each</p>
  <button type="button" data-testid="retry">Retry</button>
  <button type="button" data-testid="remove" aria-label="Remove person">x</button>
</section>
</body>
</html>
HTML
cat > src/checkout/split.css <<'CSS'
/* The split-the-bill step. */
:root {
  --color-danger: #c62828;
  --color-focus: #1d4ed8;
  --color-surface: #ffffff;
}

.split {
  display: grid;
  gap: 12px;
  padding: 16px;
  background: var(--color-surface);
}

.person-total {
  font-size: 1.125rem;
  line-height: 1.4;
  color: #c62828;
  font-weight: 600;
}

.person-card {
  min-height: 72px;
}

.empty {
  color: var(--color-danger);
}
CSS
python3 - <<'PY'
import base64

PIXEL = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
for name in ("error-built", "error-prototype", "loading-built", "empty-built"):
    with open(f"review/SPEC-220/{name}.png", "wb") as f:
        f.write(PIXEL)
PY
