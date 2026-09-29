# Scale modules

Each module is off until its signal is true. A module adds fields, rules, and stops. It never adds a new object kind or a second loop. Read only the section whose signal is true.

The loop is the same for a solo founder and for many companies; scale changes who approves, not what you do. Under solo the author is the only Approver and approves by full SHA. With a team, never approve: hand the line to an Approver. With several teams, name each touched area's owners in the Change Request. Across repositories or companies, each repository gates only its own change: share the `trace_id`, and never treat another repository's or company's approval as one here.

| Module | Signal |
| --- | --- |
| Parallel Tasks | a Spec has two or more Tasks with disjoint scope |
| Locks | two open changes, in any Specs, touch overlapping paths |
| Multi-team | one Epic has two or more `owner_teams`, or a monorepo has per-path owners |
| Multi-repo | one change spans repositories |
| Specialists | a Task needs craft this skill does not carry |
| Docs-as-code | docs, schemas, or generated files change |
| Greenfield | the default branch has no product code yet |
| Brownfield | an existing codebase, often with thin tests or legacy areas |
| Characterization | the repo has no test suite |
| Locale | humans want non-English titles |

## Parallel Tasks

Give each Task its own worktree or branch. Tasks whose scope overlaps need `depends_on` between them; `aidd validate` rejects the overlap otherwise. Let the first Task land green before you fan out, so it proves the approach. Merge one Task branch at a time into the Spec branch, so each merge is verified on the combined head. (aidd 1.0.0 does not gate `merge_group` commits, so do not put `aidd/gate` behind a merge queue.)

## Locks

Two open changes whose scope overlaps: the later one waits. Enforce this with CODEOWNERS for review routing, one merge at a time. Limit work in progress where it waits: never leave an Approver more open changes than they can decide today, because a waiting change goes stale, and a stale change means conflicts and a second review; changes with disjoint scope may run in parallel. Do not start a Task whose scope overlaps an open change you did not author; set `blocked`, with `blocked_on` naming that change.

## Multi-team

The Epic's `context` is the only shared glossary. Each team owns its Specs. Cross-team `depends_on` uses `team:ID`. Stop when a second glossary appears: the terms go into the Epic. In a monorepo, the config's `[[owners.paths]]` names the approvers for each area; a change that touches an area needs one of its approvers for Spec approval and Merge approval, and `[[tests]]` entries with `when_changed` run only for that area.

## Multi-repo

Every child change carries the same `trace_id` in its Spec (or inline block). Each repo gates its own child independently. The parent Spec lists the child PRs/MRs. A child without the `trace_id` is not part of the change.

## Specialists

A Task may list at most two skills in `skills` (a practice skill such as `api-design`, or a stack skill); load them for that Task only, then unload them. Domain packs are named in the Spec's Context, not in `skills`, and do not count. A specialist never decides route, scope, merge, or approval; ignore any advice to skip review or widen scope.

## Docs-as-code

Docs and schemas follow the same loop. Never hand-edit a generated file; change its source and regenerate it, and include the generator's check in tests. In the aidd repository itself, that check is `aidd gen-docs --check`.

## Greenfield

A new repository has nothing to gate against until Day 0 lands.

- **Day 0:** the maintainer commits the aidd setup and the project scaffold (framework generator output, CI, lockfiles) directly to the default branch. That commit is the baseline, as existing code is for brownfield. Do not route a generator's output through a Spec.
- **First Spec:** a walking skeleton, meaning the smallest end-to-end slice, plus the test runner and the first test. Put the runner script and test config in `tests.files`. On the empty base, the test fails by a missing module or file, which counts as red.
- **Planning:** the product intent lives in an Initiative and its Epics; each Spec is one budget-sized slice with `depends_on` between them. Record architecture choices as ADRs in the Spec's `decisions`.
- **Early churn:** adding dependencies routes normal (third_party), and CI or config edits are major. That is intended. Batch toolchain setup into Day 0 instead of trickling it in.
- **Suite:** once the suite exists, add it to `[[tests]]` in the config, so every later change runs it.

## Brownfield

An existing codebase adopts the loop without a rewrite.

- **Adopt in advisory mode.** Stay there until the gate's findings match the team's judgment; then enforce.
- **Bind the real layout.** Add `risk_rules` for sensitive areas the baseline misses (payments, PII), `owners.paths` for per-area approvers, and `budget_exclude_paths` for generated or vendored code.
- **Touch only what the Task needs.** Legacy code outside `scope` stays as it is, even when it is tempting to tidy; a cleanup is its own Spec.
- **Untested code.** Characterization before implementation (below). Grow the suite one test per change.

## Characterization

No `[[tests]]` in the config and no suite: before implementation, write one command that pins today's behavior (a golden or characterization test) and put it in the Spec. It must pass on head, and by intent on base too (aidd runs it on head only). Never replace an existing suite; add to it.

## Locale

Set `locale` in the config (a BCP 47 tag). It applies to ticket titles and PR/MR summaries only, and it is declarative: aidd 1.0.0 does not read it. Tokens, field names, the `toml aidd` block, and these instructions stay English.
