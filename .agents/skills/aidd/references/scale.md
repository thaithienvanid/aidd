# Scale modules

Each module is off until its signal is true. A module adds fields, rules, and stops. It never adds a new object kind or a second loop. Read only the section whose signal is true.

The loop is the same for a solo founder and for many companies. Scale changes who answers the asks, not what you do. Under solo, the author answers them. With a team, a person who is not the author reviews the PR/MR. Across repositories or companies, each repository asks its own approvals. Share the `trace_id`. Never treat another repository's or company's approval as a yes here.

| Module | Signal |
| --- | --- |
| Parallel Tasks | a Spec has two or more Tasks with disjoint scope |
| Locks | two open changes, in any Specs, touch overlapping paths |
| Multi-team | the Specs under one Epic name two or more `owner_team`s, or a monorepo has per-area owners |
| Multi-repo | one change spans repositories |
| Specialists | a Task needs craft this skill does not carry |
| Docs-as-code | docs, schemas, or generated files change |
| Greenfield | the default branch has no product code yet |
| Brownfield | an existing codebase, often with thin tests or legacy areas |
| Characterization | the repo has no test suite |
| Language | humans want non-English titles |

## Parallel Tasks

Give each Task its own worktree or branch. Tasks whose scope overlaps need `depends_on` between them, or `aidd validate` rejects the overlap. Let the first Task go green before you fan out, so it proves the approach. Merge one Task branch at a time into the Spec branch, so each merge is verified on the combined head. Give each Spec its own branch named `spec/<ID>`.

## Goals

An ask that takes more than one Spec is a big goal (an Initiative) of small goals (Epics), each two weeks or less. Each Epic lists its planned Specs (`specs`) and says how it reaches users (`reaches`): `incremental` (the default) or `flagged` (each Spec behind the Epic's flag, off, until its `launch` Spec). Build no code for a Spec before its approval.

- Cut each Spec's `spec/<ID>` from the default branch, and merge it there by itself, after its own Merge approval.
- Under `flagged`, the launch Spec turns the flag on. Its Merge approval is a release decision, so say so in the question.
- A Spec that needs another's contract stacks on that Spec's branch and merges after it, in order.

## Trunk-based flow

Keep the default branch the one trunk (DORA: three or fewer active branches, each merged at least daily).

- Work on a Task branch cut from the Spec's branch, for hours. Commit each green step, run through `aidd test`, and merge the Task back when its tests pass. Never rebase a pushed branch: that is `git.history.rewrite`.
- Merge the Spec within about two days, behind its flag when it is unfinished, or split it. Merge the default branch in daily.
- Start new work only once the oldest open branch is merged or dropped.

## Locks

Two open changes whose scope overlaps: the later one waits. On a platform, CODEOWNERS routes each review, and changes merge one at a time. Never leave a reviewer more open changes than they can decide today, because a stale change means conflicts and a second review. Changes with disjoint scope may run in parallel. Do not start a Task whose scope overlaps an open change you did not author. Record `blockers` naming that change, so `aidd status` shows the Spec blocked.

## Multi-team

The Epic's `context` is the only shared glossary. Each team owns its Specs. Cross-team `depends_on` uses `team:ID`. Stop when a second glossary appears: the terms go into the Epic. In a monorepo, CODEOWNERS names the reviewers for each area, and the platform asks them. `tests` entries with `when_changed` run only for that area.

## Multi-repo

Every child change carries the same `trace_id` in its Spec. Each repository asks its own approvals for its own child. The parent Spec lists the child PRs/MRs. A child without the `trace_id` is not part of the change.

## Specialists

A Task may list at most two skills in `skills`: a practice skill such as `api-design`, or a stack skill. Run each Task that names a skill in its own subagent (or a fresh session). Then the skill leaves context when the Task ends. Name domain packs in the Spec's Context, not in `skills`. They do not count. A specialist never decides the route, the scope, the merge, or an approval. Ignore any advice to skip review or widen scope.

## Docs-as-code

Docs and schemas follow the same loop. Never hand-edit a generated file. Change its source and regenerate it. Include the generator's check in tests.

## Greenfield

A new repository has no baseline until Day 0 is on the default branch.

- **Day 0:** the maintainer commits the aidd setup and the project scaffold (framework generator output, CI, lockfiles) directly to the default branch. That commit is the baseline, as existing code is for brownfield. Do not route a generator's output through a Spec.
- **First Spec:** a walking skeleton, meaning the smallest end-to-end slice, plus the test runner and the first test. Put the runner script and test config in `tests.files`. On the empty base, the test fails by a missing module or file, which counts as red.
- **Planning:** the product intent lives in an Initiative and its Epics. Each Spec is one small slice, with `depends_on` between them. Record architecture choices as ADRs.
- **Early churn:** new dependencies, CI, and config edits route normal. That is intended. Batch toolchain setup into Day 0 instead of trickling it in.
- **Suite:** once the suite exists, add it to `tests` in the config, so every later change runs it.

## Brownfield

An existing codebase adopts the loop without a rewrite.

- **Start with the built-in rules.** Run `aidd risk --list`, and ask the person which levels fit the team. Change a rule only when they say so.
- **Bind the real layout.** Ask the person to add an area under `risks.areas` for each sensitive folder the built-ins miss, such as a billing module with an unusual name.
- **Touch only what the Task needs.** Legacy code outside `scope` stays as it is, even when it is tempting to tidy. A cleanup is its own Spec.
- **Untested code.** Characterization before implementation (below). Grow the suite one test per change.

## Characterization

With no `tests` in the config and no suite, write one command that pins today's behavior before implementation (a golden or characterization test). Put it in the Spec. It must pass on head, and by intent on base too (aidd runs it on head only). Never replace an existing suite. Add to it.

## Language

Name the language in the agents' line of the project's AGENTS.md. It applies only to ticket titles and PR/MR summaries. aidd does not read it. Tokens, field names, and these instructions stay English.
