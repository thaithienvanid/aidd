# The loop

`SKILL.md` holds the rules and the stops. Each step says when it is done. Finish the open step before the next one. A step that waits on a person or a runner is a stop: report what it waits for.

A stage groups steps for people, and a gate is a fixed point where a person decides:

<!-- aidd:gen roles:stages -->
| Stage | Its steps | Gate |
| --- | --- | --- |
| Plan | Plan | Intent agreement (`intent.agree`), before Specify |
| Design | Specify | Spec approval (`spec.approve`), before Implement |
| Build | Implement | — |
| Test | Verify, Review | Merge approval (`pr.merge` or `git.merge`), before Merge |
| Deploy | Merge, Roll out | Production release (`deploy.run`), before Roll out |
| Maintain | Learn | — |
<!-- aidd:end -->

## The gates

You run the steps, and a person decides at each gate. Intent agreement comes only when the work has an Intent. Other `ask` actions, such as a force push, come up where they come (`references/risk.md`). Changes asked at Spec approval return to Specify, and those asked at Merge approval or in a review comment return to Implement. An incident, a rollback, or a missed hypothesis goes to Learn, and its lesson re-enters at Plan as a new change. A missed hypothesis is a person's product decision, never your fix.

Before a step, read the config's `standards` entries for your role whose `when_changed` matches the change. Plan runs first only when the request holds a goal bigger than one Spec, or several, and sorts each goal by size (`references/intents.md`). It is done when `aidd validate` passes on it and a person agrees. Learn runs on a signal and on a cadence. Only a person starts the team's autopilot command: it runs this loop and stops at each ask.

| Routes | Stages |
| --- | --- |
| minor (the default) | Build, Test, Deploy: no Spec and no Spec approval |
| normal, major | Design, Build, Test, Deploy, Maintain |
| emergency (declared) | Build, Test, Deploy, then Maintain, where the backfill Spec and Learn are due by `backfill_due` |

The `spec.approve` rule says on which routes Spec approval is asked (`aidd risk --paths` shows it). Under `team`, it is normal and major. Under `solo`, it is major only: on normal, write the Spec, say that you go on, and go on (`report`).

## Before the first edit: the route

Run `aidd risk --paths <planned paths> --change-type <change type>` (or MCP `risk`). It gives the route, whether a Spec comes first, the areas hit, the edit level, and the first step. How the route is computed: `references/routes.md`. Work on a branch of your own, never the default branch: `spec/<ID>` for a Spec, a plain name such as `fix/<topic>` otherwise. With no Spec, each commit subject starts with its type (`fix: ...`). When the real diff touches more than you planned, check again, and write a Spec if the route rises. Done when you have a route.

**Clarify first.** Never ask what the code, the docs, a standard, the project's rules, or a command settle: decide it, and list it in the handoff note's `decided`. The rest of `open_questions` become at most five questions for the author, each with your recommendation and why. Ask first what changes the route, the scope, or the Acceptance. A question that could change the route keeps confidence `low`, so stop. The others become assumptions in the Spec's `## Context`. Never guess: with two readings, the author chooses. A term the author settles goes in the glossary (`aidd new glossary`). Before Plan and Specify, run `aidd recall <the request's key words>` (MCP `recall`), and read the file a match names: the team may have decided it already. When a smaller change would do (a config value, a change with no Spec, or none), say so first.

## 1. Specify

For a normal change, `aidd new spec "<title>" --change-type <change type> --paths <planned paths>` writes the short Spec, `assets/spec-short.md`, with the route and the Task's scope. A major change on the team profile, or `--full`, gets `assets/spec.md`. Done when the Spec holds the following:

- `## Request`: the person's own words, quoted, never improved: the problem, the outcome, who is affected, the constraints, the open questions
- `## Context`: why, the relevant files, conventions, constraints, non-goals, and assumptions
- `## Acceptance`: executable (Gherkin, or a schema, table, threshold, or invariant), each item with an id (`A1`, ...). Each test command lists the ids it proves in `covers`.
- `tasks`: each with `scope`, `depends_on` (wherever scopes overlap), `risk`, and `proof`
- `tests`: `files` and `commands`, with at least one `new_behavior: true` for feat and fix, and the acceptance tests already written (hard rule 2).
- `rollback`, `risk.residual`, a `hypothesis` when the change should move a metric, and on major an `observe` block
- `## Policy conflicts`: each contradiction between specialists, a domain pack, or the project's rules, and who decides it, or `none`. Never pick a side yourself.
- the linked docs (`docs`) the change needs (`references/spec-docs.md`). On major, a tech spec with its pre-mortem and a `## Rollout`. A threat model when a dimension is security, privacy, or data.

**Spec approval.**

1. Run `aidd validate specs/<ID>.md` until 0 errors remain. Set `status: ready`, and commit the Spec, its tests, its design files, and its linked docs.
2. Ask one question with what it covers: "Approve SPEC-3? It adds a refund limit to checkout, proven by tests A1 to A4, on route major. Your yes also freezes its tests." Name the file so the person can read it. On a platform, you may open a draft PR/MR holding only those files (`pr.open`, report).
3. On the person's yes in their own words (or, under a delegation, the delegate's accept: `references/delegation.md`), set `status: approved`, `approved_by`, and `approved_at: <date and time>`. Commit it with an `Approved-by:` trailer of the same value, in the form `references/spec.md` gives, and put any detail in the commit body. Say plainly that this is a note you wrote, not proof. Then run `aidd upgrade --only ask-rules --yes` and commit its changes alone. `aidd doctor` says when the asks lag.
4. The yes covers the Spec, its tests, and its design as they read at that commit, `code.edit` inside its Tasks' `scope`, and that run. It writes an `Edit` ask for each of the Spec's test files into each agent's ask rules. After it, a change to the tests or the Acceptance is `spec.revise` (hard rule 2).
5. Start Implement only once the Spec is approved. Where `spec.approve` is `report` or `allow`, say you go on and set `status: approved` (`references/state.md`).

## 2. Implement ⟲ Verify

Commit to the same branch, one Task at a time, in `depends_on` order, and set `status: in_progress`. Tasks with disjoint `scope` run in parallel after the first Task is green (`references/scale.md`). Take in the default branch with a merge before you ask for Merge approval, never a rebase of a pushed branch. Split a change that cannot merge within a day, or hide it behind a feature flag.

**Implement.** First list what is unclear: an Acceptance gap returns to Specify, and the rest is an assumption in the Verify report. Write each unit test before its code, inside the Task's scope (red, green, refactor). Between steps, run `aidd test --no-red`, `--changed`, or one test file. Then run one full `aidd test --spec specs/<ID>.md` on the final head, or `--changed` when the team's verifier runs next. Done when:

- the diff stays inside the Task's `scope`, and no frozen test changed
- every applicable command exits 0 on the head
- every `new_behavior` command fails on base (a non-zero exit other than 126 or 127) and passes on head

**Verify.** On a green head, verify that exact commit side by side with Review (the `verifier` role, when the team runs it). On a clean tree, run the Spec's commands once; without a verifier, your last `aidd test` is that run. Then exercise each Acceptance line as a user or caller would. A gap inside the Acceptance returns to Implement, where the developer adds the test with the fix, and the verifier, which changes no tracked file, exercises the line again on the new head. A gap in the Acceptance itself is `spec.revise`. The report starts with the harness, model, and head SHA; a new push makes it stale. A failure returns to Implement, with Review's findings, in one pass.

On failure, sort it:

- your implementation is wrong: fix it, as a retry (hard rule 7)
- a test is flaky: a finding, never a retry (hard rule 7)
- a wrong Spec or a wrong test: ask for `spec.revise`, then back to Specify
- out of retries: record `waiting_on` naming the failure, until a person re-plans it

## 3. Review

Run it side by side with Verify on the same head. It counts only once Verify's report on that head is clean. Read the diff against the Spec, or the request, as an adversary would, with the repository's `REVIEW.md`. The team's `reviewer` does it, else you do. `references/state.md` says when `status` becomes `in_review`. Changes requested go back to Implement, and a new head needs a new Verify.

## 4. Merge

<!-- aidd:gen roles:merge-approval -->
- **On a local trunk**, ask in plain words: "Merge `spec/SPEC-3` into `main`? Its tests are green on `3f2c1a9`." Merge only on the person's yes, push when there is a remote, and set `status: done` when the change has a Spec.
- **On a platform under `team`**, push your branch, open or update the PR/MR (`pr.open`, report), and stop. The platform's review is the Merge approval, and its branch protection holds the merge.
- **On a platform under `solo`**, open or update the PR/MR, then ask in the chat, as on a local trunk. Merge it only on the person's yes.
<!-- aidd:end -->

Before you ask or hand back, read the platform's managed review when it runs (Claude Code Review posts Important and Nit findings, and a check run that never fails). Read its Important findings as a ranked review report: name each open one in the ask or the handoff, and send those you agree with to Implement. It is one more reviewer, never the Merge approval, which a person gives.

A new head after the yes needs a new Verify and a new ask. When only a merge of the default branch made it, and `git show --remerge-diff <merge>` prints nothing, the ask says so: what the merge brought, and that the change's own lines did not change. Verify then runs the full `aidd test` once on the new head and exercises again only the Acceptance lines the merge touched, and Review need not repeat.

## 5. Roll out and 6. Learn

Your release tooling deploys, following the Spec's `## Rollout`. A deploy you run yourself is `deploy.run`, so ask. Roll out ends when the observe window passes or the rollback trigger fires: the SRE runs the Spec's observe command, and you report. A rollback is `deploy.run` too. A rejection, a rollback, an incident, or 3 retries goes to Learn. You propose the lesson; you never adopt it. Both steps: `references/observe-learn.md`.
