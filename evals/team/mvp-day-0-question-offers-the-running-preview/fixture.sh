#!/usr/bin/env bash
set -euo pipefail
# A repository that uses aidd with an agreed MVP plan (INTENT-1) and a clean Day-0 baseline on the day0 branch: a web page
# the one-command preview serves on http://localhost:8000, with a health check that passes. The SRE's config diff names
# the preview. So the merge question offers the running preview, with its URL and what to try, and one yes covers the diff
# and the merge. The files are ours and are written only inside the case's workspace.
mkdir -p .aidd specs product/intents
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: solo

owners:
  approvers: ["@me"]
YAML
cat > BRIEF.md <<'MD'
# Request

A small web page, in Python with the standard library only, that keeps a shared shopping list: add an item, tick it
off, and see what is left. No accounts, and no network beyond this machine.
MD
cat > product/intents/INTENT-1.md <<'MD'
---
type: intent
id: INTENT-1
title: A shared shopping list on a web page
outcome: "Two people in one home keep one list for a week with no lost item"
reaches: incremental
phases:
  - id: P1
    name: Walking skeleton first
    specs:
      - {id: SPEC-1, title: "Walking skeleton: add an item, and the page shows it"}
      - {id: SPEC-2, title: "Tick an item off, and the page hides it"}
---

## Problem

- Problem: two people forget what the other added to the list.
- Appetite: two days for one person.
- Solution sketch: one page served on this machine, over one JSON file.
- No-gos: no accounts, no sync service.
- Success metric: one week of use with no lost item, checked by hand.


The stack is open: the architect decides it in Day 0's ADR.
MD
cat > specs/SPEC-1.md <<'MD'
---
type: spec
id: SPEC-1
title: Add an item and see it on the page
change_type: feat
route: normal
confidence: medium
open_questions: []
trace_id: SPEC-1
parent: INTENT-1
rollback: Revert the change.
risk:
  summary: "TODO: who or what behaves differently after this change"
  dimensions: []
  irreversible: false
tasks:
  - id: SPEC-1-T1
    title: "TODO: the first slice"
    scope: ["TODO"]
tests:
  files: ["tests/TODO"]
  commands:
    - name: acceptance
      command: ["TODO"]
      new_behavior: true
      covers: [A1]
---

## Request

"I add milk, and the page shows milk." (the slice in INTENT-1)

## Acceptance

- A1: TODO: given ..., when ..., then ...
MD
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
git add -A
git commit -q -m "docs: the agreed plan, INTENT-1, and the walking skeleton's draft Spec"
git switch -q -c day0
mkdir -p web tests scripts docs/decisions .aidd/returns/day0
cat > docs/decisions/0001-stack.md <<'MD'
# 1. Python 3.12 with the standard library, one static page

Status: accepted on the baseline's merge. `python3 -m http.server` serves `web/`, and the list lives in `web/list.json`.
MD
cat > web/index.html <<'HTML'
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Shopping list</title></head>
<body>
<main>
<h1>Shopping list</h1>
<p>Nothing on the list yet. Adding an item comes in the first slice.</p>
</main>
</body>
</html>
HTML
cat > tests/test_page.py <<'PY'
import unittest
from pathlib import Path


class PageTests(unittest.TestCase):
    def test_the_page_has_a_heading(self):
        self.assertIn("<h1>Shopping list</h1>", Path("web/index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
PY
cat > scripts/preview.sh <<'SH'
#!/usr/bin/env bash
# The one-command local preview: serve web/ on http://localhost:8000.
set -euo pipefail
exec python3 -m http.server 8000 --directory web
SH
cat > scripts/health.sh <<'SH'
#!/usr/bin/env bash
# The preview's health check: the running preview answers with the page's heading.
set -euo pipefail
python3 -c 'import urllib.request, sys; body = urllib.request.urlopen("http://localhost:8000/", timeout=5).read().decode(); sys.exit(0 if "Shopping list" in body else 1)'
echo "health: ok"
SH
chmod +x scripts/preview.sh scripts/health.sh
cat > .aidd/returns/day0/config.diff <<'DIFF'
--- a/.aidd/config.yaml
+++ b/.aidd/config.yaml
@@ -4,3 +4,7 @@

 owners:
   approvers: ["@me"]
+
+preview:
+  command: ["bash", "scripts/preview.sh"]
+  url: "http://localhost:8000"
DIFF
git add web tests scripts docs
git commit -q -m "chore: the Day-0 baseline, the SRE's scaffold

The scaffold on the stack ADR 0001 names: the page, the test runner with one passing test, the local preview
(scripts/preview.sh), and its health check (scripts/health.sh). The config diff that names the preview is in
.aidd/returns/day0/config.diff, for the lead to apply on the person's yes."
