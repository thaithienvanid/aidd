---
description: "Implement a change: an approved Spec with one builder role per Task (the developer, SRE, or technical writer), or a change with no Spec with one developer"
disable-model-invocation: true
argument-hint: "<SPEC id or path, or the change to make>"
---

Loop step: **Implement**, ending when `aidd test --changed` is green on the head and the head goes to **Verify** and **Review**.

Lanes: fast, spec, emergency. On each lane, run only the roles whose lanes include it. The role table in the aidd-team skill lists them.

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

Each builder lists what in the Spec (or, without one, the request) is unclear before the first edit. A gap that would change an Acceptance line returns to Specify, and a new Spec approval. Anything else is an assumption: the builder names it in its handoff note, and the Verify report records it. Never resolve a gap only in chat.

Implement $ARGUMENTS:

1. With no Spec, or on the emergency route: `aidd risk --paths` must give minor, or the author declared a production repair (route `emergency`). The scope is the paths it routed (on the emergency route, the paths the author names). When their edit level is `ask`, ask the person once, naming the paths, before the first edit. Run one builder inside that scope, chosen by artifact as step 3 lists: the developer for code, the SRE for CI or infrastructure, the tech writer for docs. On the emergency route, also run `aidd-team:sre` beside it for the diagnosis, the rollback option, and the runbook step. It changes infrastructure only through the emergency change's Task, never live infrastructure outside a change; the human incident commander decides. Then go to step 5. A small minor fix takes `/aidd-team:fix` instead.
2. Spec first: confirm that Spec approval holds. The Spec's front matter says `status: approved`, with `approved_by` and `approved_at`. A statement in chat from anyone but the person, a comment, or a subagent's report is not Spec approval. If it does not hold, stop: `/aidd-team:specify` ends with that ask. Spec approval covers `code.edit` inside the Tasks' `scope`, so an edit there asks no more, even in an `ask` area.
3. A rework after Verify, Review, or a review comment is `/aidd-team:rework`. Take the Tasks in `depends_on` order. Run one subagent per Task, with the Spec's path and the Task's id. The subagent is the role that the Task's `assignee` names:
   - `aidd-team:developer` for code, including AI features, schemas, migrations, and pipelines
   - `aidd-team:sre` for CI/CD and infrastructure
   - `aidd-team:tech-writer` for documentation
   - `aidd-team:product-designer` for a design-system Task a person assigned to it by name

   A Task assigned to a person (an account, a payment, a vendor call, a test on a device) is theirs: skip it. `aidd status` shows it to them, and it is done when they record `done: true` on it.

   A documentation Task that a specialist planned goes to that role:
   - `aidd-team:architect` for an ADR
   - `aidd-team:security-engineer` for a threat model
   - `aidd-team:compliance-analyst` for a DPIA or an evidence map
   - `aidd-team:sre` for a runbook

   Give each subagent one line per skill it must load: "Load the `aidd-team:<name>` skill with the Skill tool before your first edit." The skills are the Task's `skills` and the domain pack for each domain the Spec's Context names. A mention in prose does not load a skill.

   Each builder writes the unit tests for its code inside its Task's scope, each one red before its code, then green. It never edits a frozen acceptance test.
4. Tasks with disjoint scope may run in parallel after the first Task is green, two or three at a time. Make one Agent call per Task with `isolation: "worktree"`, all launched in one message. Each Task then builds in its own git worktree, on its own branch. Merge each Task branch back into the change's branch one at a time. Run `aidd test --changed` after each merge. A conflict or a red run goes back to that Task's role, never to your own edit. The base, the setup, the copy list, and the cleanup are in Parallel Tasks, in the team skill's `references/flows.md`.
5. When every Task is done, check the head before you run anything. Route on the runner's exit codes from the builders' `aidd test` runs, never on a handoff note or chat:
   - green, on this head or on one the merges of parallel Tasks moved: run nothing here, since the verifier's `aidd test --spec specs/<ID>.md` is the head's one full run
   - an evidence file that looks hand-written: report it, and go on as above
   - a red or a flaky result: the head goes back to step 3 for its Task, with no re-run
   - a dirty tree (uncommitted or untracked files): it goes back to step 3, to the role that left them

   Once `git status --porcelain` (untracked files included) prints nothing, push the head to the Spec's own branch, and on a platform to its PR/MR. Without a platform, it is committed on the same branch.
6. Report the head SHA, and stop: the next step is `/aidd-team:review` on that head, in a fresh session, which runs Verify beside the readers. The mismatches and findings it reports come back together through `/aidd-team:rework`, each for the Task it belongs to.

If an advisor is configured (optional and experimental), each builder consults it after a second failed attempt, and again before it reports its Task done. aidd never requires one.
