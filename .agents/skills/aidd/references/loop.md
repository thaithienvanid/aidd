# The loop

The only process file; the rules and the stops it points to are in `SKILL.md`. Each step has a done-gate. Finish the open gate before the next one. A gate that needs a human or a runner is a stop for you: report what it waits for.

```text
(Plan) → Specify → [Spec approval] → Implement ⟲ Verify → Review → [Merge approval] → Ship → (Learn)
```

## Two loops

The outer loop is human strategy and governance: it decides what is worth doing (Plan), whether you may start (Spec approval), whether it may merge (Merge approval), whether and how it ships (Ship), and whether the process changes (Learn). The inner loop is yours: Specify, Implement ⟲ Verify, Review. You draft the contract in Specify, Spec approval freezes it, and you then work inside it, iterating until the runner is green or you are blocked.

**Human feedback** sends work back, and it is a normal part of the loop: Spec approval with changes requested returns to Specify; Merge approval with changes requested, or a review comment, returns to Implement; Ship sends an incident, a rollback, or a missed hypothesis to Learn; Learn's lesson re-enters at Plan as a new change. A missed hypothesis is a product decision for a person at Plan, never a fix you start on your own. The loop contract has a version (1.0.0); a change that adds, removes, or reorders a step, an approval, or a lane bumps its major number.

**House standards.** Before a step, read the house standards listed for your role whose `when_changed` matches the change: `aidd owners --json --changed <paths>` lists them under each role's `house_standards` (config.md, `[[standards]]`). One marked "enforced by" a test is checked by the gate; one marked "guidance" is checked by the reviewer, so cite it when you depart from it.

Two artifacts cross, and both are machine-checkable. Inward, the Spec approval hash freezes the Spec, its tests, and its design files, so you cannot move the target you are graded against. Outward, the gate record carries the runner's exit codes bound to a head and base SHA. Your prose is never evidence: the gate binds to the hash, the exit codes, and the SHAs, and never to a summary, a claim that tests pass, or a chat handoff. Humans do read your ranked report and your handoff note's Needs line — that is what Merge approval and the stop list are for — but nothing a human reads that way makes the gate pass. That is why every stop in this file is a report and never an assertion.

The entry rule picks the lane (section 0); run only its steps. Plan runs before the loop only when the work is bigger than one Spec. Learn runs after it on a signal (a Merge approval rejection, a rollback, an incident, or three failed retries) and on a cadence, as a retrospective on the loop itself. On the emergency lane, Learn's lesson is a regression test that reproduces the incident, linked from `outcome.learn_ref`.

| Lane | Routes | Steps | What the gate asks |
| --- | --- | --- | --- |
| Fast (the default) | minor, standard | Implement ⟲ Verify → Review → Ship | the repo suite on head; one Merge approval (none for standard) |
| Spec | normal, major (computed) | Specify → Spec approval → Implement ⟲ Verify → Review → Merge approval → Ship | tests with red-then-green; Spec and Merge approval; a specialist reviewer and an observe block on major |
| Emergency | emergency (declared) | Implement ⟲ Verify → Review → Ship → Learn | smoke tests; the commander and the approvals; the backfill Spec and review by `review_due` |

## 0. The entry rule: `aidd next`

Every change starts with `aidd next`, which computes the minimum route from the paths and picks the lane; the gate recomputes it from the real diff and can only raise it. The route is the way into the loop, not a step of it, and computing it takes seconds. The fast lane is the default: a change starts there unless the computed minimum route needs a Spec.

Done when you have chosen a route: `minor` or `standard` (the fast lane, no Spec; `standard` only for a pre-approved class), `normal` or `major` (the spec lane; the route computed from the paths may be major, so you may declare `normal` and the gate raises it), or `emergency` (a production repair the author declares), and recorded `type`, `risk` (summary, dimensions, reversible), `confidence`, `open_questions`, and a `trace_id`. Use `aidd next` (or the MCP `next` tool) for the branch's diff, `aidd new spec --paths` for planned paths before any code, and `references/routes.md`. On major, add the specialist review and the `observe` block the gate will ask for.

**Clarify first: the entry rule's precondition.** Turn `open_questions` into at most five questions for the author, ordered by whether the answer changes the route, the scope, or the acceptance. A question whose answer could change the route keeps confidence `low`, so you stop; the others become assumptions in the Spec's `## Context`, where a reviewer can challenge them. Never guess an answer to write a cleaner Spec. When the request has more than one reasonable reading, present the readings and let the author choose; never pick one silently. When a smaller change would do (a config value, a fast-lane change, or no change at all), say so before writing a Spec: pushing back is part of the way in.

Stops: `SKILL.md` stops 1 and 2.

## 1. Specify

Done when the Spec file holds the following (`aidd new spec` writes the short Spec, `assets/spec-short.md`, for a normal change: Intent, Acceptance, Design, and Rollback, where Intent carries the why; a major Spec, or `--full`, is `assets/spec.md` with every section):

- `## Intent`: the originator's own words, written before any design: the problem, the outcome they want, who is affected, the constraints, and the open questions. Quote them; do not improve them.
- `## Context`: why, the relevant files, conventions, constraints, and non-goals
- `## Acceptance`: executable. Use Gherkin for user-visible behavior, and a schema, table, threshold, or invariant otherwise. Give each item an id (`A1`, `A2`, ...) and name the ids each test command proves in its `covers`; `aidd validate` then warns about an Acceptance item no command covers.
- `tasks`: each with `scope` (its files), `depends_on` (its order, required wherever scope overlaps), `risk` (what it could break and how it guards against that), and `proof` (the test, screenshot, or check that shows it works)
- `tests`: `files` plus `commands`. At least one `new_behavior = true` command for feat and fix changes; set `new_behavior = false` on refactor, docs, and build tests, which pass on base too. List the files the tests run through (a Makefile target, test config) in `tests.files` as well, so Spec approval freezes them.
- the test files themselves, already written
- `rollback`, `residual_risk`, and an `observe` block on major
- a `hypothesis` when the change is meant to move a metric: the metric, its baseline, the expected move, and by when; Learn records `outcome.result` against it
- `## Policy conflicts`: where specialist input, a domain pack, or org policy contradict each other, each conflict and the human who must decide it; `none` when there are none. Never resolve a conflict yourself by picking a side.
- on major, a pre-mortem: assume the change failed in production and write why; each cause becomes a test, a rollback step, or an observe signal

`aidd validate specs/<ID>.md` reports 0 errors (a TODO in a `command`, a `scope`, or `tests.files` is an error).

**Spec approval.**

1. Fill `assisted_by`, then commit the Spec, its tests, and its design files and open a draft PR/MR holding only those files, with `spec = "specs/<ID>.md"` in its Change Request block from the start (without a platform, they stay on the branch). Its tests are expected to fail until Implement, and `aidd/gate` lists the Spec approval it waits for.
2. Run `aidd hash specs/<ID>.md --comment` and give the printed line, `/aidd approve-spec <ID> <hash> <commit>`, to the author in chat; an Approver (someone in `owners.approvers` other than the author) posts it on the PR/MR. With no platform, the person runs `aidd approve spec specs/<ID>.md` at their own terminal instead, and later `aidd approve merge` and `aidd ship`; never run any of the three yourself.
3. The hash covers the Spec (except `status`, `blocked_on`, `outcome`, and `retry_count`), every test file, and every design file (`design.files`: mockups, wireframes, flows), so any later change to one voids the approval.
4. Do not start Implement until Spec approval holds on the routes in the profile's `spec_approval_routes`. The stricter rule is deliberate. A statement in chat, even from an Approver, is not Spec approval: only the `aidd/gate` status, or a local `aidd gate` after a person's `aidd approve spec`, shows it.
5. Once Spec approval holds, set the Spec's `status = "ready"`. `status` is outside the hash, so this voids nothing, and from then on the edit-time hook denies every edit to the frozen test and design files instead of waiting for the gate to notice.

Stops: `SKILL.md` stops 1 and 9.

## 2. Implement ⟲ Verify

Push implementation commits to the same draft PR/MR (hard rule 13). One Task at a time, in `depends_on` order. Tasks with disjoint `scope` may run in parallel, one worktree or branch each, after the first Task lands green: it proves the approach before you fan out.

**Small batches.** Keep the branch short-lived: rebase onto the base branch, or merge it in, before you ask for Merge approval, not after; a merge after Merge approval changes the head, so it needs a new Verify and a new approval. Ship a feature that cannot go whole behind a feature flag rather than on a long branch. A change that cannot merge within a day is split into smaller Specs; the route budgets exist so that a review stays small enough to be real.

**Parallel by scope, limited by humans.** Run in parallel whatever has disjoint scope: Tasks in worktrees after the first Task lands green, and separate changes. The limit is on humans, not on you: never leave an Approver more open changes than they can decide today (three is a good default); when their queue is full, finish, split, or park a change as `blocked` before opening another. There are no sprints, estimates, or status meetings: a change ships when the gate is green, its size is its route budget, and the gate's status says where it is.

**Implement.** Check as you go, not after: call `check_edit` (or let the edit-time hook do it) before editing, and run `aidd test --spec specs/<ID>.md` after each step. Done when the diff stays inside the Task's `scope`, you have not touched a test file, every applicable test command exits 0 on the current head, and every `new_behavior` command fails on the base commit (red: a non-zero exit other than 126 or 127) and passes on head (green). A compile or import error on base also counts as red. Every changed line obeys hard rule 10 (minimum change). Done means verified (hard rule 11): run the repository's tests, `aidd test`, and `aidd gate`, and paste their output into your handoff; fix the code, not the test. In CI, the `aidd-tests` job is the runner of record; a non-zero exit, a timeout, or a runner that did not start is a fail, and prose never passes.

**Verify.** Once the head is green, verify that exact commit, as a step of its own (the `verifier` role, when the team runs it): run the Spec's test commands on the head, then exercise the built change against each Acceptance line the way a user or caller would. Start the report with the head SHA you checked; a new push makes it stale, and Verify runs again. A failure or a mismatch returns to Implement; a clean report hands the head to Review. The report only routes the work: the evidence is still the runner's exit codes.

On failure, sort it:

- implementation error or flake: retry, increment `retry_count`, maximum 3
- wrong Spec or wrong test: back to Specify, then a new Spec approval
- at 3 retries: status `blocked`, `blocked_on` names the failure

## 3. Review

Start once Verify's report on this exact head is clean. Mark the PR/MR ready for review (minor, standard, and emergency: open it with the inline Change Request block from `assets/change-request.md`). Without a platform, the branch is ready when `aidd gate` waits only on Merge approval, which a person records with `aidd approve merge`. The gate derives everything else from the platform: changed paths, line counts, test results, approvals, identities, and the Policy answer.

**Merge approval** holds when:

- as many eligible Approvers as the profile requires for the route (`gates.approvals`) approved the current head
- the Approver is not an author or an agent (except under the solo profile), and approval comments are new, unedited, and outside quotes or code blocks
- major also has an approval from each specialist pool its reasons name (team and up): `security`, `data`, `privacy`, `finance`, or `compliance`, from `owners.reviewers`
- nobody whose approval the change needs (Approver, specialist reviewer, path owner) has requested changes
- Policy allows. A freeze passes only for route emergency.

Changes requested, or a review comment that needs code, go back to Implement; the new head needs a new Verify and a new Merge approval. You never merge. The platform merges once the `aidd/gate` status is green; without a platform, a person runs `aidd ship`.

## 4. Ship

The platform merges and your release tooling deploys, progressively on major. Ship ends when the observe window passes (`aidd observe <spec> --write` at its start and end) or the rollback trigger fires. You report; a person runs the rollback and records the outcome. See `references/observe-learn.md`.

## 5. Learn, on a signal or a cadence

On a reject, a rollback, an incident, or a Task that hit 3 retries, write the lesson into a change (a PR/MR, or a branch without a platform) against `AGENTS.md`, a skill, or a test, and link it in `outcome.learn_ref`.

Every incident becomes a permanent check (a regression test, plus an eval scenario when an agent's behavior caused it), the second mistake goes into the instructions, and the instruction file stays about one page: `references/observe-learn.md` has each rule.

On a cadence (every two weeks or 20 merged changes), run a retrospective on the loop itself: `aidd metrics <events.jsonl> --since <last retrospective>`, the postmortems, and the review findings. Keep or revert last cycle's improvements on their numbers, then propose at most three new ones, each with a metric, a target, and a check date. Each one re-enters the loop at Plan as a new change, which starts with `aidd next`: a Spec for this repository or the org preset, an RFC for the method, a test for an escaped defect. You propose; you never adopt. Process files are protected paths, so a human decides, and a proposal that loosens a control must cite the metric that justifies it.

## Handoff note

When you stop, for any reason, end with the handoff note, and write it into the Spec (below its sections) or the PR/MR body as a fenced block with the info string `aidd-handoff`, holding TOML:

````text
```aidd-handoff
done = "T1: total() returns 0 for an empty cart (src/cart.py); aidd test green on 3f2c1a9"
next = "verifier"        # the role that takes the work next, or "spec-approval" or "merge-approval"
needs = "none"           # a decision only a person can give, in one sentence, or "none"
stopped_at = "none"      # the stop rule that fired, or "none"
spend = "41k tokens"     # optional
```
````

Append a new block each time; the latest one counts. `aidd next` reads it: `next` names who has the work ("your agent (verifier)"), `spec-approval` or `merge-approval` puts the Spec in the Approver's inbox, and a `needs` other than none becomes a step for a person. The note is a report, never evidence: the gate does not read it, and the Spec approval hash leaves out every `aidd-handoff` block, so writing one never voids Spec approval. After a compaction, read your latest note back and continue from `stopped_at`.

## Emergency lane

The repair is Implement, its smoke tests the Verify step; Ship needs the route's approvals plus an approval from the named commander, a human in `owners.approvers` who is not an author, and a specialist review when a protected path changes. The inline block names `severity`, `kind`, `commander`, and `review_due` (within `emergency.review_sla_days`, default 2, of the day the change opened or its head was last pushed, whichever is later), plus `backfill`: commit that stub in the same change (`aidd new spec INC-<n> --title "<incident>" --route emergency`, with the same `review_due`). It may ship under freeze. After the release, finish the backfill Spec, run the review, write the regression test that reproduces the incident (and an eval scenario when an agent's behavior caused it), and record its link in `outcome.learn_ref` by `review_due`; `aidd validate` fails once it is overdue.
