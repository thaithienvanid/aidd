# Intents

The Intent above a Spec, from the request it answers to the person's agreement. A Proposal, before any commitment, is in `references/proposal.md`. `aidd validate` is the authority.

## The request and the Intent

A request is the person's own words, from the chat or a file such as `BRIEF.md`, never rewritten. Sort each goal in it by size, as you sort a request. A minor fix needs no Spec, and a one-change goal gets its own Spec, whose `## Request` quotes its words. Write a one-change goal's Spec at the split (`aidd new spec "<title>"`). A goal bigger than one Spec gets an Intent, `product/intents/INTENT-<n>.md` (`aidd new intent`), quoting them in `## Problem`. When unsure, the product manager judges the size. Each Intent's `request` names the request's file. A chat request gets one first: the product manager saves the words once, as given, and nothing else, to `specs/requests/<yyyy-mm-dd>-<slug>.md`. It is committed, so it leaves out secrets, credentials, and others' personal data (names, emails, phone numbers, addresses, customer records), each marked, as `[left out: a customer's email]`. A quote of the request, in an Intent's `## Problem` or a Spec's `## Request`, leaves out the same, with the same marks. Pasted material (a log, an email thread) becomes a line of what and from where. aidd reads no file there as a work item, and `aidd validate` flags a secret's known shape.

The Intent's fields, past those a Spec shares (`references/spec.md`):

<!-- aidd:gen fields:intent~spec -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `type` | `"intent"` | yes | Object type. Always `intent`. |
| `id` | string | yes | Intent key, such as INTENT-3. |
| `title` | string | yes | One line. The language in the project's AGENTS.md may apply. |
| `outcome` | string | yes | One sentence of what will be true once the Intent is done. The measures that say so are its `success_criteria`. |
| `serves` | string | no | The one item of the product scope this Intent serves: a product outcome or a standing outcome (`Outcome-n`), or a requirement (`Requirement-n`) of a BRD when there is no PRD and no standing outcomes. Never an objective: it is served through the outcome or requirement that serves it. Once a product scope exists, `aidd validate` errors on an Intent with none, and on an id that is missing, retired, or of the wrong kind. |
| `success_criteria` | list of mapping (`criterion`) | no | How a person will know the outcome was reached: one measure for each criterion, each with its own day to read it. Required with `serves`. A criterion is a line under its Intent, not a work item: it has no status of its own, and its address (`INTENT-1#S1`) names it in `from`. |
| `request` | string | no | The request it answers, the person's own words: a path, such as `BRIEF.md` or a saved chat request, `specs/requests/<yyyy-mm-dd>-<slug>.md`, or a link. aidd never changes it. |
| `from` | string \| string \| string | no | What raised this Intent: an item id, a criterion's address (`INTENT-1#S1`), `band:<id>`, or a link. Leave it out when a person asked for the work. An Intent that a proposal raised names the proposal in `proposal` or here, never in both. |
| `status` | `intent_status` | no | Only a person closes an Intent, because only a person can say its goal is met or dropped: they set `done`, or `cancelled` to stop it. Draft, approved, and active are derived from the approval and the slices. `approved` has no stored form, because nothing a person writes sets it: `approval` and the commit that holds it do, and a file that says `status: approved` is refused. |
| `approval` | mapping (`decision`) | no | A person's yes to the Intent: `{by, at}`, set by `aidd approve <id>`, never an agent. It holds only by its commit, as the common schema's `decision` says. A change to the Intent after it, apart from the fields an agent keeps current, such as `blocked_by` and a slice's `merged_in`, warns until they approve again. |
| `waiting_on` | string | no | Role, person, or interface the Intent waits on. While `waiting_on` names one, the Intent is blocked: `aidd status` shows it as a flag, not a status. |
| `blocked_by` | list of string | no | The work items this Intent waits for before its work starts, by id: no Spec under it starts until they finish. `aidd validate` checks that they form no cycle. |
| `development_team` | string | no | The development team accountable for the outcome: a key of the config's `development_teams`, which `aidd validate` checks. Its Specs are the team's work too. A slice may name another team in its own `development_team`. |
| `trace_id` | string | no | Joins this Intent with the Specs of other repositories that deliver its slices: each sets `trace_id: <home>-<Intent id>`. |
| `reaches` | `incremental` \| `flagged` \| `batched` | no | How the work reaches users, agreed with the Intent. `incremental` (the default): each Spec merges by itself. `flagged`: each merges behind a flag that stays off until the last slice of the last phase, whose Merge approval is the launch, which a person always decides. `batched`: the Specs build on `intent/<ID>`, which one Merge approval merges. |
| `covers` | list of string | no | The ids of the proposal needs this Intent delivers, when it came from an accepted proposal. |
| `proposal` | string | no | The accepted proposal this Intent delivers, so every change under it traces back to what was promised. |
| `start_on` | string | no | The day a person chose for the work to start. |
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

## Slices

A slice is a planned Spec: one line in a phase, with its `id` and `title`. It may add `blocked_by`, `development_team`, `repo`, `merged_in`, and `drafted_in`.

- Plan writes no Spec file. When a slice's work starts, `aidd new spec <ID>` writes its Spec from the line, or from the draft `drafted_in` names. `blocked_by` and `development_team` move into the Spec.
- A slice carries no route: `aidd risk --paths` gives it when the work starts. A slice that routes minor gets no Spec file, and its line records `merged_in: <sha>`.
- `aidd validate` checks the slice ids are unique and `blocked_by` has no cycle. A Spec's `parent` is an Intent that lists it.

## Intent approval

A person approves each Intent before any Spec's work starts (`intent.approve`, an `ask`). Ask one question for the split. Name what each goal becomes (its Intent, its Spec, or a minor fix), the saved file, and what was left out: "Saved your request to specs/requests/<file>, leaving out 1 customer email. Approve INTENT-1 and INTENT-2, with SPEC-4 for the export and a minor fix for the typo?" On the yes, each Spec goes to Specify, and each minor fix runs with no Spec. Set each Intent's `approval: {by, at}`, and change nothing else in it, in one commit whose last paragraph holds an `Approved-by:` line of the same person and `Approves:` with each Intent's id, such as `Approves: INTENT-1, INTENT-2`. A file is never their yes: an `approval` with no such commit reads as draft. A headless run cannot answer the commit's prompt, so it stops with `aidd status <ID>` on `needs`. That gives the person `aidd approve <IDs>`, which records them all as their own act. Never run `aidd approve` yourself.

## Phases and stages

A phase is a roadmap group of an Intent's slices. A stage is where one change stands in the loop: Plan, Design, Build, Test, Deploy, or Maintain (`references/graph.md`). Say both, as "Phase 1 · Walking skeleton: SPEC-1 in Test".

## Trackers

A tracker keeps its own initiatives, epics, and order. The repository keeps the Intent, the Spec, its tests, and every approval. The Intent's `tracker` lists `{type, id}` entries, and a Spec's its story. Plan asks once which records hold the work. An enabled connector reads them and writes back each merged SHA (`message.send`, asked once per Intent); with none, the person does.
