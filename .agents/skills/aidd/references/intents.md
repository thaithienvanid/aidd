# Intents

The Intent above a Spec, from the request it answers to the person's agreement. A Proposal, before any commitment, is in `references/proposal.md`. `aidd validate` is the authority.

## The request and the Intent

A request is the person's own words, from the chat or a file such as `BRIEF.md`, never rewritten. Sort each goal in it by size, as you sort a request. A minor fix needs no Spec, and a one-change goal gets its own Spec, whose `## Request` quotes its words. A goal bigger than one Spec gets an Intent, `specs/INTENT-<n>.md` (`aidd new intent`), quoting them in `## Problem`. When unsure, the product manager judges the size. Each Intent's `request` names the request's file. A chat request gets one first: the product manager saves the words once, as given, and nothing else, to `specs/requests/<yyyy-mm-dd>-<slug>.md`. It is committed, so it leaves out secrets, credentials, and others' personal data (names, emails, phone numbers, addresses, customer records), each marked, as `[left out: a customer's email]`. A quote of the request, in an Intent's `## Problem` or a Spec's `## Request`, leaves out the same, with the same marks. Pasted material (a log, an email thread) becomes a line of what and from where. aidd reads no file there as a work item, and `aidd validate` flags a secret's known shape.

The Intent's fields, past those a Spec shares (`references/spec.md`):

<!-- aidd:gen fields:intent~spec -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `type` | `"intent"` | yes | Object type. Always `intent`. |
| `id` | string | yes | Intent key, such as INTENT-3. |
| `title` | string | yes | One line. The language in the project's AGENTS.md may apply. |
| `goal` | string | yes | The measurable goal of an Intent. |
| `request` | string | no | The request it answers, the person's own words: a path, such as `BRIEF.md` or a saved chat request, `specs/requests/<yyyy-mm-dd>-<slug>.md`, or a link. aidd never changes it. |
| `status` | `intent_status` | no | Only a person closes an Intent, because only a person can say its goal is met or dropped: they set `done`, or `cancelled` to stop it. Draft and active are derived from its slices. |
| `agreed_by` | string | no | The person who agreed, in `approved_by`'s form, never an agent. `aidd upgrade` never writes it. |
| `agreed_at` | string | no | When the person agreed (RFC 3339). A slice added or removed, or a new `goal`, after it warns until they agree again. |
| `blocked_by` | list of string | no | The work items this Intent waits for before its work starts, by id: no Spec under it starts until they finish. `aidd validate` checks that they form no cycle. |
| `delivery_team` | string | no | The delivery team accountable for the outcome: a key of the config's `delivery_teams`, which `aidd validate` checks. Its Specs are the team's work too. A slice may name another team in its own `delivery_team`. |
| `trace_id` | string | no | Joins this Intent with the Specs of other repositories that deliver its slices: each sets `trace_id: <home>/<Intent id>`. |
| `reaches` | `incremental` \| `flagged` \| `batched` | no | How the work reaches users, agreed with the Intent. `incremental` (the default): each Spec merges by itself. `flagged`: each merges behind a flag that stays off until the last slice of the last phase, whose Merge approval is the launch, which a person always decides. `batched`: the Specs build on `intent/<ID>`, which one Merge approval merges. |
| `covers` | list of string | no | The ids of the proposal needs this Intent delivers, when it came from an accepted proposal. |
| `proposal` | string | no | The accepted proposal this Intent delivers, so every change under it traces back to what was promised. |
| `go_no_go` | mapping (`go_no_go`) | no | A person's decision to pursue the Intent or not, in the proposal's shape; `no_go` derives `cancelled`. Never an agent's. |
| `phases` | list of mapping (`phase`) | no | The phases, in order, each an ordered group of slices. An Intent with one phase lists that one. |
| `tracker` | list of mapping | no | The tracker's records this Intent links to, such as `{type: epic, id: PORT-31}`. aidd calls no tracker. |
| `risks` | list of mapping (`raid_item`) | no | The R of the RAID log, copied from the accepted proposal and kept current here. |
| `assumptions` | list of mapping (`raid_item`) | no | The A of the RAID log, copied from the accepted proposal and kept current here. |
| `issues` | list of mapping (`raid_item`) | no | The I of the RAID log, copied from the accepted proposal and kept current here. |
| `dependencies` | list of mapping (`raid_item`) | no | The D of the RAID log, copied from the accepted proposal and kept current here. |
| `decisions` | list of mapping (`decision`) | no | The scope decisions log, copied from the accepted proposal and kept current here. Each entry is a person's decision. |
<!-- aidd:end -->

`aidd validate` warns when `## Problem` cites no source: a link, a path, a quote with its source, or a dated note. Mark a guess "(assumed)". Only a person records `go_no_go`.

Each Intent's `## Request coverage` traces the whole request: a row per success criterion and hard constraint, naming its proof (`SPEC-1 A3`, `exit: P1`), another goal's Intent or Spec that covers it (`INTENT-2`, `SPEC-4`), `deferred, asked: <question>`, or `the request's non-goal`. Write a one-change goal's Spec at the split (`aidd new spec "<title>"`), so the row names a Spec that exists. `aidd validate` errors on an empty row, a row naming none of these, or a slice or phase this Intent does not list. It errors on a work item that does not exist or is this Intent, a line the first slice lacks, or Intents that only name each other. A row matches a sibling's row by its words, so each Intent of a request writes an item the same. A closed Intent or a missing table warns.

## Slices

A slice is a planned Spec: one line in a phase, with its `id` and `title`. It may add `blocked_by`, `delivery_team`, `repo`, `merged_in`, and `drafted_in`.

- Plan writes no Spec file. When a slice's work starts, `aidd new spec <ID>` writes its Spec from the line, or from the draft `drafted_in` names. `blocked_by` and `delivery_team` move into the Spec.
- The first slice also gets 2 to 5 acceptance lines and its order of work (`### First slice`).
- A slice carries no route: `aidd risk --paths` gives it when the work starts. A slice that routes minor gets no Spec file, and its line records `merged_in: <sha>`.
- `aidd validate` checks the slice ids are unique and `blocked_by` has no cycle. A Spec's `parent` is an Intent that lists it.

## Intent agreement

A person agrees to each Intent before any Spec's work starts (`intent.agree`, an `ask`). Ask one question for the split. Name what each goal becomes (its Intent, its Spec, or a minor fix), the saved file, and what was left out: "Saved your request to specs/requests/<file>, leaving out 1 customer email. Agree to INTENT-1 and INTENT-2, with SPEC-4 for the export and a minor fix for the typo?" On the yes, each Spec goes to Specify, and each minor fix runs with no Spec. Set each Intent's `agreed_by` and `agreed_at`, in one commit with an `Agreed-by:` trailer of the same value. A file is never their yes. A headless run cannot answer the commit's prompt, so it stops with `aidd status <ID>` on `needs`. That gives the person `aidd agree <IDs>`, which records them all as their own act. Never run `aidd agree` yourself.

## Phases and stages

A phase is a roadmap group of an Intent's slices. A stage is where one change stands in the loop: Plan, Design, Build, Test, Deploy, or Maintain (`references/loop.md`). Say both, as "Phase 1 · Walking skeleton: SPEC-1 in Test".

## Trackers

A tracker keeps its own initiatives, epics, and order. The repository keeps the Intent, the Spec, its tests, and every approval. The Intent's `tracker` lists `{type, id}` entries, and a Spec's its story. Plan asks once which records hold the work. An enabled connector reads them and writes back each merged SHA (`message.send`, asked once per Intent); with none, the person does.
