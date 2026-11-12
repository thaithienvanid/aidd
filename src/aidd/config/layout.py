"""Where aidd writes, by one rule (docs/architecture/README.md, "Where aidd writes").

- A file directly in `.aidd/` is committed: the config, and what `aidd init` keeps beside it (`harness-rules.json`,
  `team-files.json`).
- A folder in `.aidd/` is aidd's own output for this worktree, which git ignores (OUTPUT_IGNORE): the test evidence,
  with the preview captures beside it, and the pages `aidd explore` and `aidd prototype` write.
"""

from __future__ import annotations

EVIDENCE_DIR = ".aidd/evidence"
VIEWS_DIR = ".aidd/views"
# The one .gitignore line `aidd init` writes: every folder in .aidd/, never a file there.
OUTPUT_IGNORE = "/.aidd/*/"
# The harness ask rules `aidd init` and `aidd upgrade` wrote, so they change only their own entries (risk.harness_rules).
HARNESS_RULES_FILE = ".aidd/harness-rules.json"
# The team files `aidd init --aidd-team` and `aidd upgrade` wrote, by path and SHA-256, so they remove only those (setup.team_record).
TEAM_FILES_FILE = ".aidd/team-files.json"
