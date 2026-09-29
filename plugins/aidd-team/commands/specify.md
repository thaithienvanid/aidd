---
description: "Specify a Spec with the architect, the product designer for user-facing changes, the security engineer and compliance analyst when risky, the SRE, and the tester, then prepare Spec approval"
argument-hint: "<SPEC id or path>"
---

Loop step: **Specify**, ending at **Spec approval**. Spec lane only. Every change starts with `aidd next`, the loop's entry rule: it computes the minimum route from the paths and picks the lane.

Lanes: spec.

Specify $ARGUMENTS as a team:

1. Run `aidd next` (before any code, `aidd new spec <ID> --paths <planned paths>`). When it says minor or standard, this is the fast lane: stop, and use `/aidd-team:implement` without a Spec. A production repair is the emergency lane, declared by the author, never computed: follow it instead.
2. Run the `aidd-team:architect` subagent: scope, design, decisions, Tasks, risk, and rollback. It writes the planned paths as the Tasks' scope and keeps the route at least what `aidd next` computes. Before Spec approval the team writes only the Spec and its tests; ADRs, threat models, and runbooks become documentation Tasks written after Spec approval.
3. **Assign the Tasks.** The architect assigns each Task by artifact, never by stack (`assignee = "agent:developer"` for application code of any layer, `agent:ml-engineer`, `agent:data-engineer`, `agent:platform-engineer`, or `agent:tech-writer`; a documentation Task a specialist planned goes to that specialist: `agent:architect` for an ADR, `agent:security-engineer` for a threat model, `agent:compliance-analyst` for a DPIA or an evidence map, `agent:sre` for a runbook), names the domain packs the change touches in the Spec's Context, and puts the practice skill for each Task's kind of work in the Task's `skills` (`api-design`, `schema-migration`, `accessible-ui`, `ai-evals`, at most two); the guard then lets only that role write the Task's scope.
4. Run the specialists that apply **in parallel**, each as a reader that returns its part in its fixed template (the aidd skill's Spec reference, Specialist returns); the architect then folds each into the Spec section the template names, so one writer holds the file:
   - a user-facing surface: `aidd-team:product-designer` for the flow, every screen state, and copy in `design.files`, which Spec approval freezes with the Spec
   - major, a security, data, privacy, compliance, or third_party dimension, or an AI feature: `aidd-team:security-engineer` for the threat model, the ASVS level, and the security tests it hands to the tester
   - compliance or data dimensions, a regulated profile, or an AI feature above the minimal EU AI Act tier: `aidd-team:compliance-analyst` for obligations, controls, and a DPIA plan
   - major, or a profile that requires observe: `aidd-team:sre` for the SLO-based observe block, the rollback trigger, a runbook, and the pre-mortem
5. The architect folds every section in and records the open questions that remain as assumptions in `## Context` (the aidd skill's Clarify rule).
6. Run the `aidd-team:tester` subagent, last and alone, on the folded Spec: Acceptance, tests for every condition and abuse case (and visual, accessibility, and eval tests from the design and AI thresholds), each new-behavior test seen failing on the current code.
7. Run `aidd validate` on the Spec; loop back to the right role until it reports 0 errors.
8. Commit the Spec, its tests, and its design files, open a draft PR/MR with `spec = "specs/<ID>.md"` in the Change Request block (without a platform, keep them on the branch), and run `aidd hash <spec> --comment`.
9. Give the author the approval line, and stop: Spec approval is a human decision, posted on the PR/MR or, without a platform, recorded by a person with `aidd approve spec`.
