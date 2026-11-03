"""Where aidd writes, by one rule (docs/ARCHITECTURE.md, "Where aidd writes").

- A file directly in `.aidd/` is committed: the config, and what `aidd init` keeps beside it (`harness-rules.json`).
- A folder in `.aidd/` is aidd's own output for this worktree, which git ignores (OUTPUT_IGNORE): the test evidence,
  with the preview captures beside it, and the pages `aidd explore` and `aidd prototype` write.
"""

from __future__ import annotations

EVIDENCE_DIR = ".aidd/evidence"
VIEWS_DIR = ".aidd/views"
# What the verifier captured for people, beside the evidence.
PREVIEW_DIR = f"{EVIDENCE_DIR}/preview"
# The one .gitignore line `aidd init` writes: every folder in .aidd/, never a file there.
OUTPUT_IGNORE = "/.aidd/*/"
# The harness ask rules `aidd init` and `aidd upgrade` wrote, so they change only their own entries (risk.harness_rules).
HARNESS_RULES_FILE = ".aidd/harness-rules.json"
