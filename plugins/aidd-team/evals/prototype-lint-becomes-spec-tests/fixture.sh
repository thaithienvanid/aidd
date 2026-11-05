#!/usr/bin/env bash
set -euo pipefail
# SPEC-220 with its one-file prototype and the tokens the generated block comes from. The screen holds the violations
# the prompt shows. The files are ours and are written only inside the case's workspace.
mkdir -p .aidd specs/SPEC-220/design design
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: team

owners:
  approvers: ["@org/leads"]
YAML
cat > specs/SPEC-220.md <<'MD'
---
aidd_version: "1.0.0"
type: spec
id: SPEC-220
title: Split the bill at checkout
status: draft
---

## Intent

After the cart, a customer splits the total between up to four people.

## Design

The prototype is `specs/SPEC-220/design/prototype.html`, built on `design/tokens.json`.
MD
cat > design/tokens.json <<'JSON'
{
  "color": {
    "surface": { "$value": "#ffffff", "$type": "color" },
    "text": { "$value": "#1a1a1a", "$type": "color" },
    "danger": { "$value": "#c62828", "$type": "color" }
  },
  "space": {
    "3": { "$value": "12px", "$type": "dimension" }
  }
}
JSON
cat > specs/SPEC-220/design/prototype.html <<'HTML'
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Split the bill</title>
<style id="tokens">
  :root { --color-surface: #ffffff; --color-text: #1a1a1a; --color-danger: #c62828; --space-3: 12px; }
</style>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter">
<style>
  .card { background: var(--color-surface); color: #1a1a1a; padding: var(--space-3); }
  .total { color: rgb(200, 30, 30); }
</style>
</head>
<body>
<section data-screen="split">
<div class="card">
  <h2>Lorem ipsum dolor</h2>
  <p>Your Name owes 12.50</p>
  <div class="icon-btn" onclick="split()">✂️</div>
  <img src="https://images.example.com/avatar.png">
  <!-- TODO: real copy -->
</div>
</section>
</body>
</html>
HTML
