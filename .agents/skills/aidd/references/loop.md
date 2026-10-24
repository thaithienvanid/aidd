# The loop

`SKILL.md` holds the rules and the stops it points to. Each step says when it is done. Finish the open step before the next one. A step that waits for a human or a runner is a stop for you: report what it waits for.

```text
(Plan) → Specify → [Spec approval] → Implement ⟲ Verify → Review → [Merge approval] → [Publish] → Roll out → (Learn)
```

## Two loops

Humans own the outer loop: Plan, Spec approval, Merge approval, Publish, Roll out, and Learn. You own the inner one: Specify, Implement and Verify until green, then Review. No role runs a loop of its own. Changes requested at Spec approval return to Specify; at Merge approval or in a review comment, to Implement. An incident, a rollback, or a missed hypothesis goes to Learn, and its lesson re-enters at Plan as a new change. A missed hypothesis is a person's product decision, never your fix.

Before a step, read your role's standards whose `when_changed` matches the change (`aidd owners --json --changed <paths>`).

The route sets the lane. Run only its steps. Plan runs first only when the work is bigger than one Spec; it is done when `aidd validate` passes on its files and a person agrees. Learn runs on a signal and on a cadence. Only a person starts autopilot (`/aidd-team:autopilot`, or `/aidd-autopilot`). Under it, do exactly the action `aidd autopilot next` gives, and never pick the work yourself.

| Lane | Routes | Steps | What the gate asks |
| --- | --- | --- | --- |
| Fast (the default) | minor, standard | Implement ⟲ Verify → Review → Merge approval → Publish → Roll out | the repo suite on head; one Merge approval (none for standard) |
| Spec | normal, major (computed) | Specify → Spec approval → Implement ⟲ Verify → Review → Merge approval → Publish → Roll out | red-then-green tests; Spec and Merge approval; on major a specialist Approver, and an observe block unless only a protected path made it major |
| Emergency | emergency (declared) | Implement ⟲ Verify → Review → Merge approval → Publish → Roll out → Learn | smoke tests; the commander; the backfill Spec by `review_due` (`references/emergency.md`) |

## Before the first edit: the route

Ask the gate: `aidd gate --paths <planned paths> --type <type>` (or MCP `gate`) gives the route, the lane, why, and the first step. On a branch, `aidd gate` computes it from the diff. `aidd new spec --paths` computes the same and exits 1 when no Spec is needed. How the route is computed: `references/routes.md`. Work on a branch of its own, never the base branch: `spec/<ID>` for a Spec, a plain name such as `fix/<topic>` otherwise. Done when you have a route. A Spec records `type`, `risk`, `confidence`, `open_questions`, and `trace_id`. On the fast lane, each commit subject starts with its type (`fix: ...`), which the gate reads. When `aidd gate` on the branch gives a route above the forecast, leave the fast lane. Write the Spec and its tests for the branch as it is, and ask for Spec approval. You may declare `normal` where the gate raises it to major.

**Clarify first.** Never ask what the code, the docs, a standard, the project's rules, or a command settle: decide it, and list it in the handoff note's `decided`. The rest of `open_questions` become at most five questions for the author, each with your recommendation and why. Ask first what changes the route, the scope, or the acceptance. A question that could change the route keeps confidence `low`: stop. The others become assumptions in the Spec's `## Context`. Never guess: with two readings, the author chooses. A term the author settles goes in the glossary (`aidd new glossary`). When a smaller change would do (a config value, a fast-lane change, or none), say so first.

Stops: `SKILL.md` stops 1 and 2.

## 1. Specify

For a normal change, `aidd new spec <ID> --title "..." --type <type> --paths <planned paths>` writes the short Spec, `assets/spec-short.md`, with the computed route and the Task's scope. A major change, or `--full`, gets `assets/spec.md`. Done when the Spec holds the following:

- `## Intent`: the originator's own words, quoted, never improved: the problem, the outcome, who is affected, the constraints, the open questions
- `## Context`: why, the relevant files, conventions, constraints, non-goals, and assumptions
- `## Acceptance`: executable (Gherkin, or a schema, table, threshold, or invariant), each item with an id (`A1`, ...). Each test command lists the ids it proves in `covers`. `aidd validate` warns on an id no command covers.
- `tasks`: each with `scope`, `depends_on` (wherever scopes overlap), `risk`, and `proof`
- `tests`: `files` (with the config they run through, so approval freezes it) and `commands`, with at least one `new_behavior: true` for feat and fix. Also the test files themselves, already written
- `rollback`, `residual_risk`, a `hypothesis` when the change should move a metric, and on major an `observe` block unless only a protected path made it major
- `## Policy conflicts`: each contradiction between specialists, a domain pack, or org policy, and who decides it, or `none`. Never pick a side yourself.
- the linked docs (`docs`) when the change needs more (`references/spec.md`). On major, a tech spec (with its pre-mortem) and a rollout runbook, unless only a protected path made it major. A threat model before Spec approval when a dimension is security, privacy, or data. A test plan, prototype, or ADR when they earn their place.

`aidd validate specs/<ID>.md` reports 0 errors.

**Spec approval.**

1. Fill `assisted_by`. Commit the Spec, its tests, design files, and linked docs. Under `publish: agents`, push and open a draft PR/MR holding only those. Otherwise keep them on the branch: `aidd publish` carries the approval later.
2. Ask the person to type `approve <ID>`: aidd records it, or posts it on the PR/MR as them. `aidd hash specs/<ID>.md --summary --html` writes the Spec approval page, and `aidd gate --html` the Merge approval page. A page never approves, and the gate never reads it.
3. The hash covers the Spec (except the bookkeeping: `status`, `blockers`, `outcome`, `labels`, `relations`, `triage`, `priority`, `owner`, `assisted_by`, and a Task's `retry_count` and `done`), every test file, every design file, and every frozen linked doc (`docs` unless `frozen: false`). Any later change to one of them voids the approval. A drift found in Implement goes in the verification report and a later docs-only change. Sign-offs humans give after approval go in the living acceptance record (`aidd new acceptance`).
4. Start Implement only once Spec approval holds (the profile's `spec_approval_required_routes`). `aidd/gate` shows it. With no gate workflow in the repository (`aidd init --ci none`), check locally with `aidd gate --spec specs/<ID>.md`. A chat message never does. Set no status beyond what `references/state.md` names.

Stops: `SKILL.md` stops 1 and 9.

## 2. Implement ⟲ Verify

Commit to the same branch, and its PR/MR once published (hard rule 10), one Task at a time in `depends_on` order. Tasks with disjoint `scope` run in parallel after the first Task lands green (`references/scale.md`). Take in the base branch with `aidd sync`, never a rebase, before you ask for Merge approval, not after. A merge after it changes the head and needs a new Verify and a new approval. Split a change that cannot merge within a day, or hide it behind a feature flag.

**Implement.** First list what is unclear: an Acceptance gap returns to Specify, the rest is an assumption in the Verify report. Run `check_edit` before an edit you are unsure about. Between steps, run `aidd test --no-red`, `--changed`, or one test file; then one full `aidd test --spec specs/<ID>.md` on the final head, or `--changed` when the team's verifier runs next. Done when:

- the diff stays inside the Task's `scope`, and no test file changed
- every applicable command exits 0 on the head
- every `new_behavior` command fails on base (a non-zero exit other than 126 or 127) and passes on head

Done means verified (hard rule 9): paste that `aidd test` and `aidd gate`. If a test fails, fix the code, not the test.

**Verify.** On a green head, verify that exact commit side by side with Review (the `verifier` role, when the team runs it). On a clean tree, run the Spec's commands once, the head's one full run. Without a verifier, your last `aidd test` in Implement is that run. Then exercise each Acceptance line as a user or caller would. The report starts with the harness, the model, and the head SHA, and a new push makes it stale. A failure or a mismatch returns to Implement, with Review's findings, in one pass.

On failure, sort it:

- your implementation is wrong: fix it. Each fix is one retry (`retry_count`), at most 3
- a test is flaky: a finding, never a retry and never re-run until it passes (hard rule 8)
- wrong Spec or wrong test: back to Specify, then a new Spec approval
- at 3 retries: record `blockers` naming the failure. The Task shows as stopped, and the Spec as blocked, until a person re-plans it

## 3. Review

Run it side by side with Verify on the same head. It counts only once Verify's report on that head is clean. Read the diff against the Spec, or the ask, as an adversary would, with the repository's `REVIEW.md`: the team's `reviewer` does it, else you do. Mark the PR/MR ready once it is published. Add a Change Request block only where `assets/change-request.md` says a change needs one. For each gate finding, `aidd gate --explain <code>` gives its fix. Without a platform, the branch is ready when `aidd gate` waits only on Merge approval. What Merge approval needs: `references/gate.md`.

Changes requested go back to Implement. A new head needs a new Verify and a new Merge approval. You never merge. Then the person types `land it`, or on a platform trunk `publish`, then `merge it`.

## 4. Roll out and 5. Learn

Once it landed and the person published it, your release tooling deploys, following the runbook the Spec links. Roll out ends when the observe window passes (`aidd observe <spec> --write`) or the rollback trigger fires. You report, and a person runs the rollback. A rejection, a rollback, an incident, or 3 retries goes to Learn. You propose it; you never adopt it. Both steps: `references/observe-learn.md`.

## Handoff note

When you stop, for any reason, end with the handoff note as an `aidd-handoff` block. `references/handoff.md` gives its fields and where it goes.
