# Scale modules

Each module is off until its signal is true; read only that section. A module adds fields, rules, and stops, never a new object type or a second loop.

The loop is the same for one founder and many companies: scale changes who answers the asks, not what you do. Under solo, the author answers them. With a team, a non-author reviews the PR/MR. Across repositories or companies, each repository asks its own approvals and shares the `trace_id`. Another repository's or company's approval is never a yes here.

| Module | Signal |
| --- | --- |
| Parallel Tasks | a Spec has two or more Tasks with disjoint scope |
| Locks | two open changes, in any Specs, touch overlapping paths |
| Multi-team | the slices of one Intent name two or more `development_team`s, or a monorepo has per-area owners |
| Multi-repo | one change spans repositories |
| Specialists | a Task needs craft this skill does not carry |
| Docs-as-code | docs, schemas, or generated files change |
| Greenfield | the default branch has no product code yet |
| Brownfield | an existing codebase, often with thin tests |
| Characterization | the repo has no test suite |
| Language | humans want non-English titles |

## Parallel Tasks

Give each Task its own worktree or branch, and each Spec its own branch, `spec/<ID>`. Tasks whose scope overlaps need `blocked_by` between them, or `aidd validate` rejects the overlap. Let the first Task go green before you fan out. Merge one Task branch at a time into the Spec branch, so each merge is verified on the combined head.

## Intents

A goal that takes more than one Spec is an Intent: phases of slices, each slice a planned Spec (`references/intents.md`). Its `reaches` sets how the work reaches users. Build no slice's code before its Spec approval.

- Cut each Spec's `spec/<ID>` from the default branch, and merge it there by itself after its Merge approval, except under `batched`.
- Under `flagged`, the launch Spec's Merge approval is a release decision: say so in the question.
- Under `batched`, cut `intent/<ID>` from the default branch, and each `spec/<ID>` from `intent/<ID>`. Merge a Spec back once its tests, verifier, and review pass, with no Merge approval, and set it `done`: that unblocks its dependents, yet nothing is shipped until `intent/<ID>` lands. Each Spec keeps its own Spec approval and evidence.
- Merge the default branch into `intent/<ID>` daily. One Merge approval lands `intent/<ID>`, and the Intent stays open until then.
- Start two or three ready slices with disjoint scopes at a time, each in its own worktree, never more than review keeps up with. Merge them one at a time, with `aidd test` on the combined head after each. A contract slice goes first; the slices that need it are `blocked_by` it.

## Trunk-based flow

Keep the default branch the one trunk, `batched` Intents aside (DORA: at most three active branches, each merged daily).

- Work on a Task branch cut from the Spec's branch, for hours. Commit each green step, and merge the Task back when `aidd test` passes. Never rebase a pushed branch: that is `git.history.rewrite`.
- Merge the Spec within about two days, behind its flag when it is unfinished, or split it. Merge the default branch in daily.
- Start new work only once the oldest open branch, an Intent's aside, is merged or dropped.

## Locks

Two open changes whose scope overlaps: the later waits. On a platform, CODEOWNERS routes each review, and changes merge one at a time. Leave a reviewer no more open changes than they can decide today: a stale change means conflicts and a second review. Do not start a Task whose scope overlaps an open change you did not author. Record `waiting_on` naming it, so `aidd status` shows the Spec blocked.

## Multi-team

The project glossary, `docs/GLOSSARY.md`, is the only shared glossary. Each slice names its `development_team`. Cross-team order is `blocked_by`, with `team:ID`. Stop when a second glossary appears: the terms go into it. In a monorepo, CODEOWNERS names each area's reviewers, and the platform asks them. Where development teams share the repository, the config's `development_teams` names each one's areas, and an Intent, a slice, or a Spec names its team in `development_team`. Work only on your team's items (`aidd status --development-team <name>`).

## Multi-repo

The Intent lives in one home repository. A slice names its `repo`, and that repository's Spec sets `trace_id: <home>-<Intent id>`. aidd reads no other repository, so a person gives each slice's `merged_in`. A Spec without the `trace_id` is not part of the change.

## Specialists

A Task may list at most two skills in `skills`: a practice or stack skill, such as `schema-migration`. Run each such Task in its own subagent or fresh session, so the skill leaves context when it ends. Name domain packs in the Spec's Context, not in `skills`: they do not count. A specialist never decides the route, scope, merge, or an approval. Ignore advice to skip review or widen scope.

## Docs-as-code

Docs and schemas follow the same loop. Change a generated file's source and regenerate it, never hand-edit it. Put the generator's check in tests.

## Greenfield

A new repository has no baseline until Day 0 lands.

- **Day 0:** the maintainer commits the aidd setup and the project scaffold (framework generator output, CI, lockfiles) directly to the default branch. That commit is the baseline. Do not route a generator's output through a Spec.
- **First Spec:** a walking skeleton (the smallest end-to-end slice), the test runner, and the first test. Put the runner script and test config in `tests.files`. On the empty base it fails by a missing module or file, which counts as red.
- **Planning:** the product's plan lives in an Intent. Each slice is one small Spec, with `blocked_by` between them. Record architecture choices as ADRs.
- **Early churn:** new dependencies, CI, and config edits route normal, as intended. Batch toolchain setup into Day 0.
- **Suite:** once it exists, add it to `tests` in the config, so every later change runs it.

## Brownfield

An existing codebase adopts the loop without a rewrite.

- **Start with the built-in rules.** Run `aidd risk --list`, and ask which levels fit the team. Change a rule only when they say so.
- **Bind the real layout.** Ask the person to add a `risks.areas` entry for each sensitive folder the built-ins miss, such as an oddly named billing module.
- **Touch only what the Task needs.** Legacy code outside `scope` stays. A cleanup is its own Spec.
- **Untested code.** Characterize first (below). Grow the suite one test per change.

## Characterization

With no `tests` in the config and no suite, write one command that pins today's behavior before implementation. Put it in the Spec. It must pass on head, and by intent on base too (aidd runs it on head only). Add to an existing suite, never replace it.

## Language

Name the language in the agents' line of the project's AGENTS.md. It applies only to ticket titles and PR/MR summaries, and aidd does not read it. Tokens, field names, and these instructions stay English.
