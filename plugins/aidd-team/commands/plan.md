---
description: "Plan work as an Initiative, Epics, and Spec stubs with the product manager"
disable-model-invocation: true
argument-hint: "<idea or request>"
---

Loop step: **Plan**, before the loop, only for work bigger than one Spec.

Lanes: spec.

<!-- aidd:gen roles:lead -->
**You are the lead.** You run this command and the roles do its work:

1. You route, and you place each role: play it yourself, or start it. Play only a role that adds a view to work you are writing, for a small step, when your session runs on its tier. Take its pack with `aidd context <ID> --role <role> --play --session ${CLAUDE_SESSION_ID}`, so the guard holds you to its files, and run `--stop-playing` when the step ends, before you start a role. Never play a role that checks, tests, or reviews work you wrote. The verifier, the reviewer, the security engineer, the compliance analyst, and the designer's review always start. Never write both the tests and the code. Start a role too when a cheaper tier does it, it works in parallel on its own scope, or it would fill your context. Under autopilot, start every role. Pass on each role's handoff note.
2. Hand each role you start the paths it reads, never pasted facts or a summary. With a Spec, that is its context pack, `aidd context <ID> --role <role>`, else the files by path. It returns its work in the file it owns, and its handoff note.
3. Launch the roles of one group in parallel, in one message, and wait for all of them before you act. Do not take a turn per completion. A role that returns no report ran out of turns: never take silence as done; start it again on what is left, from the files it wrote, and after two silent runs ask the person.
4. Pass the `model` in every Agent call: the one the role's agent file names, which follows its tier (`opus` for reasoning, `sonnet` for execution). Read-only search helpers (Explore) take the execution tier's model.
5. Start each command in a fresh session (or after `/clear`). It begins from the files and the latest handoff note, never from an earlier command's conversation.
6. A revision changes each affected section with one Edit (Write only a new or mostly rewritten file). It reruns only the roles whose part the new facts change.
7. End with the handoff note, its Spend line included, and stop where the command stops.
8. Take only the team's decisions, each on its evidence, never an approval: Who decides what, in the roles reference (the aidd-team skill's `references/roles.md`, or `.aidd/team-roles.md`), lists them. Sort each request first: a question (answer it from the files), new work (triage), a change to an approved Spec (`aidd revise`), or a production repair (the emergency route).
<!-- aidd:end -->

Run the `aidd-team:product-manager` subagent on this request: $ARGUMENTS. For a new product built from a brief, `/aidd-team:mvp` runs the plan and the build together.

Each question it asks the author comes with its recommended answer and why. It looks up what the repository answers, and never asks it.

**Milestones come from the person.** The plan records a milestone on the Initiative (`milestones`: a name, the date, and the Specs whose landing reaches it) only when the person names a date or a release. It never invents a date, and never turns a size into one. With no date named, the plan is an ordered list of slices, and `aidd list` shows what lands next.

**Consult round.** When the product manager returns a draft, ask the roles whose view the plan needs, in parallel, in one message, each for a perspective card on the draft. Each returns the card in its final message and edits no file:
- `aidd-team:architect`, always: is each stub feasible as cut, the hard parts, the shape, and a size per stub (S, M, L).
- `aidd-team:product-designer`, when the work has a user-facing surface: the flows and screens it implies, and what the stubs miss.
- `aidd-team:security-engineer`, when a stub touches security, data, privacy, money, or AI: the risks, and the stubs they move.
- `aidd-team:domain-expert`, when the work sits in a domain a domain pack covers (payments, health, children, the public sector, and the rest): the domain's rules, the cases the plan misses, the words it uses wrongly. Name the packs it loads.

A card has four lines: Assessment (feasible, at risk, or not feasible as cut), Hard parts, Change (to which stubs, and why), Size. Then run the product manager once more with the cards. It revises the stubs, and records each card and what changed in the Initiative's `## Perspectives` section. One round only: a disagreement left goes to the author as a question with a recommended answer.

When it returns, show the author the Initiative, the Epics in order, and the Spec stubs. Give how each Epic reaches users (`incremental`, `flagged`, or `batched`), the sizes, and the risks the cards named. Then stop. Planning is done only when a human agrees to it. That decision stays theirs under a standing approval too. The plan goes on its own branch. The person lands it as soon as they agree (`land it`), so it merges with the Initiative and the Epics only, since a stub fails `aidd validate` until Specify fills it. Then:
- An Epic that is `batched`: `aidd goal open <EPIC>` cuts its goal branch, `goal/<EPIC>`, from the default branch. Each of its Specs starts on `spec/<ID>`, cut from the goal branch. `aidd new spec <ID> --parent <EPIC>` names the goal as the Spec's base. The team integrates each finished Spec (`aidd integrate`). A person releases the goal once.
- An Epic that is `incremental` or `flagged`: each Spec starts on `spec/<ID>`, cut from the default branch, and lands there by itself. Under `flagged`, each lands behind the Epic's flag, off. Its `launch` Spec turns the flag on, and a person gives that launch's Merge approval.

The gate gives each Spec's route before the first edit (`aidd gate --paths`). A Spec that depends on another starts after that one lands. A new product's first slice is its walking skeleton (`skeleton: true` on its Task): the structure, the contracts, the test runner, CI, and one smoke test. The architect or the SRE builds it before the other slices fan out. When the slices share a contract (an API, a schema, or the types they all use), its Spec goes first. The others carry `relations: [{type: blocked_by, id: <the contract's Spec>}]`: they are specified in parallel and implemented once the contract has landed. Autopilot runs independent Specs side by side (`autopilot.parallel`), and the person approves the ready ones together with one typed `approve`. A new ask that fits an agreed Epic's scope becomes a Spec there. A new slice is a new Epic, and the person agrees to the plan again. The Initiative, the Epics, and the stubs are files in the repository. Mirroring them to a tracker is optional, and only when the project already has one connected.
