"""A work item's folder: everything about an Initiative, an Epic, or a Spec lives beside its file, in `specs/<ID>/`.

`specs/SPEC-12.md` is the work item. `specs/SPEC-12/` holds what it links and what was decided for it: its linked
documents (`<type>-<topic>.md`, such as `tech-spec-checkout.md`), its design files (`design/`, frozen by Spec
approval when `design.files` names them), and its explorations (`explore/<slug>/`, each with `exploration.md`).
`docs/` holds the project's official docs: the ADRs, the architecture overview, the runbooks, the glossary.

This module names the folder's parts.
"""

from __future__ import annotations

DESIGN_FOLDER = "design"
EXPLORE_FOLDER = "explore"
EXPLORATION_FILE = "exploration.md"
