---
description: "Ship an approved change: after Merge approval and the merge, run the observe window with the SRE and follow the rollback trigger"
argument-hint: "<SPEC id or path>"
---

Loop step: **Ship**, on the spec and emergency lanes. Start only when Merge approval holds and the change has merged; the merge itself is a human's.

Lanes: spec, emergency. A fast-lane change has no observe window: its Ship is the human's merge.

1. Run the `aidd-team:sre` subagent for $ARGUMENTS, and in parallel `aidd-team:platform-engineer` for the rollout mechanism and `aidd-team:compliance-analyst` for the audit evidence map when the Spec has compliance obligations. The merged change's scope is closed, so the compliance analyst returns the map as obligation, control, and evidence rows in its return template (the aidd skill's Spec reference), which go into the ship report; writing it under `docs/compliance/` is a documentation Task in a follow-up change whose scope covers that path.
2. The SRE owns the report: `aidd observe <spec>` at the start and end of the window, a comparison with the SLO and the rollback trigger, and a report to the author. Agents report; a person records the result in the Spec's `outcome` (`aidd observe <spec> --write`).
3. If the trigger fires, say so first and stop: a person runs the rollback and records it, and the loop goes to Learn (`/aidd-team:postmortem`).
4. Optional, after a clean window: when the merged Spec's Design changed the system's shape, offer the author a follow-up change that folds it into `docs/architecture/`, the living architecture docs, as its own change through the loop. Open it only if the author agrees.
