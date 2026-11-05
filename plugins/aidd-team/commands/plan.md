---
description: "Plan work bigger than one Spec as an Intent, phases of slices, with the product manager"
disable-model-invocation: true
argument-hint: "<idea or request>"
---

Loop step: **Plan**, in the Plan stage, only for work bigger than one Spec. It ends at the Intent agreement gate.

Lanes: spec.

<!-- aidd:gen roles:lead -->
**You are the lead.** You run this command and the roles do its work:

1. You route, and you place each role: play it yourself, or start it. Play only a role that adds a view to work you are writing, for a small step, when your session runs on its tier. Read its agent file, and keep to its area until the step ends. Never play a role that checks, tests, or reviews work you wrote. The verifier, the reviewer, the security engineer, the compliance analyst, and the designer's review always start. Never write both the tests and the code. Start a role too when a cheaper tier does it, it works in parallel on its own scope, or it would fill your context. Pass on each role's handoff note.
2. Hand each role you start the paths it reads, never pasted facts or a summary: the Spec, its linked docs, and the files by path. Name the practice skills for the files it writes, except one its agent file preloads, and it loads them before it writes those files: for code, `maintainable-code` and `secure-coding`; for docs, `plain-language`; for a UI, `accessible-ui`. It returns its work in the file it owns, or a part another role folds in `.aidd/returns/<ID>/<role>.md`, and names that file on its handoff note.
3. Launch the roles of one group in parallel, in one message, and wait for all of them before you act on their work. A role that returns no report, or a partial one, stopped at its turn cap: never take it as done. Resume that agent, which keeps its history, and ask for its report; where you cannot, start it again from the files it wrote. After two such stops, ask the person.
4. Pass the `model` in every Agent call: the one the role's agent file names, which follows its tier (`opus` for reasoning, `sonnet` for execution). Read-only search helpers (Explore) take the execution tier's model.
5. Start each command in a fresh session (or after `/clear`). It begins from the files and the latest handoff note, never from an earlier command's conversation.
6. A revision changes each affected section with one Edit (Write only a new or mostly rewritten file). It reruns only the roles whose part the new facts change.
7. End with a handoff note that `aidd validate` passes: every required key, no other key, and `stopped_at` starting with a stop code. Include its Spend line, and stop where the command stops.
8. Take only the team's decisions, each on its evidence, never a person's: Who decides what, in the roles reference (the aidd-team skill's `references/roles.md`, or `.aidd/team-roles.md`), lists them. A role's `ask` comes to you: ask the person in plain words, and on their yes, do the action. A proposed edit comes as a unified diff in `.aidd/returns/`, which the person reads and you `git apply` on the yes. Spec approval covers `code.edit` in its Tasks' `scope`, so it asks no more there. Sort each request first: a question (answer it from the files), new work (triage), a change to an approved Spec (`spec.revise`), or a production repair (the emergency route).
9. Under a standing delegation in Claude Code, run `aidd delegate check` before a delegated ask. On `eligible`, start aidd-team:delegate with the action, the command the check covered, and the head, and nothing else. Act only on its accept: run that exact command, or commit the Spec's approval with the check's three trailers, never `Approved-by`. On a defer, ask the person, once. Never answer for the delegate.
<!-- aidd:end -->

Run the `aidd-team:product-manager` subagent on this request: $ARGUMENTS. The request, or the file it names, is the brief: the person's own words. The product manager writes the Intent (`specs/INTENT-<n>.md`) beside it, never over it. For a new product built from a brief, `/aidd-team:mvp` runs the plan and the build together.

Each question it asks the author comes with its recommended answer and why. It looks up what the repository answers, and never asks it. It asks once about a tracker: "Does a tracker hold this work's initiative or epics, and which?" Through the project's own enabled connector, it reads them and links them in the Intent's `tracker`. With no connector, the person gives the ids.

**The Intent traces the brief.** Each success criterion and hard constraint of the brief is a row of `## Brief coverage`, with the slice that proves it, `deferred, asked`, or `the brief's non-goal`. The product manager never drops, cuts, or softens a decision the brief records (a decision log, non-goals, named tools) without asking. A proposed cut is its own question, never folded into the agreement's yes. It never re-asks what the brief settled.

**The first slice carries its work.** It gets 2 to 5 acceptance lines and its order of work in the Intent, so a builder can start it the day after agreement. Later slices stay one line until their work starts.

**Dates come from the person.** A phase gets a `due` date only when the person names a date or a release. The plan never invents a date, and never turns a size into one. With no date named, the phases are an ordered list of slices, and `aidd status` shows what comes next.

**Consult round.** When the product manager returns a draft, ask the roles whose view the plan needs, in parallel, in one message, each for a perspective card on the draft. Each returns the card in its final message and edits no file:
- `aidd-team:architect`, always: is each slice feasible as cut, the hard parts, the shape, and a size per slice (S, M, L).
- `aidd-team:product-designer`, when the work has a user-facing surface: the flows and screens it implies, and what the slices miss.
- `aidd-team:security-engineer`, when a slice touches security, data, privacy, money, or AI: the risks, and the slices they move.
- `aidd-team:domain-expert`, when the work sits in a business domain a business pack covers, such as payments and finance: the domain's rules, the cases the plan misses, the words it uses wrongly. Name the packs it loads. A business pack's skill has a Terms section. A technology pack, such as web front end, starts none: the roles that load it apply its checklist.

Size the round to the plan. When the draft holds one slice, ask the architect alone, because Specify brings in the other roles. Never start a role whose card would repeat another.

A card has four lines: Assessment (feasible, at risk, or not feasible as cut), Hard parts, Change (to which slices, and why), Size. Then run the product manager once more with the cards. It revises the slices, and records each card and what changed in the Intent's `## Perspectives` section. One round only: a disagreement left goes to the author as a question with a recommended answer.

When it returns, ask "Agree to INTENT-<n>?" in one short question (`intent.agree`). Say what the person gets, the first thing they can click, the phases, how the work reaches users, and the risks the cards named. Link the Intent. Then stop: planning is done only when a person agrees. On their yes, set `agreed_by` and `agreed_at`, commit them with an `Agreed-by:` trailer of the same value. Then merge the plan's branch, which holds the Intent alone: a slice gets its Spec file only when its work starts. Then:
- `reaches: incremental` or `flagged`: each Spec starts on `spec/<ID>`, cut from the default branch, and merges there by itself. Under `flagged`, each merges behind the flag, off. Its `launch` Spec turns the flag on, and a person gives that launch's Merge approval.
- `reaches: batched`: each Spec starts on `spec/<ID>`, cut from the default branch. Its Specs reach users together, in one release a person decides.

**Slices start in phase order.** When a slice's work starts, `aidd new spec <ID>` writes its Spec from the line, and `aidd risk --paths` gives its route before the first edit. A new product's first slice is its walking skeleton (`skeleton: true` on its Task): the structure, the contracts, the test runner, CI, and one smoke test. The architect or the SRE builds it before the other slices fan out. When slices share a contract (an API, a schema, or the types they all use), its slice goes first. The others are `blocked_by` it: they are specified in parallel and implemented once the contract is merged. Start ready slices two or three at a time, never more than review keeps up with. The lead may ask for the approval of the ready ones in one question. A new ask becomes a slice in its phase, and the person agrees to the Intent again. The Intent is a file in the repository, and a tracker only links to it.
