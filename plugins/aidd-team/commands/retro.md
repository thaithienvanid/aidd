---
description: "Run a retrospective on the AIDD loop itself with the agile coach, and propose measured improvements"
disable-model-invocation: true
argument-hint: "[since date, such as 2026-09-11]"
---

Loop step: **Learn**, on the team's cadence (`autopilot.retro_every` merged changes, or every two weeks) and after every Learn signal.

Lanes: fast, spec, emergency.

<!-- aidd:gen roles:lead -->
**You are the lead.** You run this command and the roles do its work:

1. You route, and you place each role: play it yourself, or start it. Play only a role that adds a view to work you are writing, for a small step, when your session runs on its tier. Take its pack with `aidd context <ID> --role <role> --play --session ${CLAUDE_SESSION_ID}`, so the guard holds you to its files, and run `--stop-playing` when the step ends, before you start a role. Never play a role that checks, tests, or reviews work you wrote. The verifier, the reviewer, the security engineer, the compliance analyst, and the designer's review always start. Never write both the tests and the code. Start a role too when a cheaper tier does it, it works in parallel on its own scope, or it would fill your context. Under autopilot, start every role. Pass on each role's handoff note.
2. Hand each role you start the paths it reads, never pasted facts or a summary. With a Spec, that is its context pack, `aidd context <ID> --role <role>`, else the files by path. It returns its work in the file it owns, and its handoff note.
3. Launch the roles of one group in parallel, in one message, and wait for all of them before you act. Do not take a turn per completion. A role that returns no report, or a partial one, stopped at its turn cap: never take it as done. Resume that agent, which keeps its history, and ask for its report; where you cannot, start it again from the files it wrote. After two such stops, ask the person.
4. Pass the `model` in every Agent call: the one the role's agent file names, which follows its tier (`opus` for reasoning, `sonnet` for execution). Read-only search helpers (Explore) take the execution tier's model.
5. Start each command in a fresh session (or after `/clear`). It begins from the files and the latest handoff note, never from an earlier command's conversation.
6. A revision changes each affected section with one Edit (Write only a new or mostly rewritten file). It reruns only the roles whose part the new facts change.
7. End with the handoff note, its Spend line included, and stop where the command stops.
8. Take only the team's decisions, each on its evidence, never an approval: Who decides what, in the roles reference (the aidd-team skill's `references/roles.md`, or `.aidd/team-roles.md`), lists them. Sort each request first: a question (answer it from the files), new work (triage), a change to an approved Spec (`aidd revise`), or a production repair (the emergency route).
<!-- aidd:end -->

Run the `aidd-team:agile-coach` subagent for the period since $ARGUMENTS (default: the last file in `docs/retros/`):

1. `aidd metrics <events.jsonl> --since <last retrospective>` on the gate events, and `--roles` for one row per role.
2. The postmortems, review findings, the feedback log (`aidd digest` counts its themes), and the support the delivery manager reported against the contract's levels, since then.
3. Last cycle's improvements kept or reverted on their numbers.
4. `aidd eval standards` for every role or domain standard past its review cadence or its `review_due`. Where the project runs a weekly standards check, also read its latest `aidd eval standards --online` report for quotes moved or missing.
5. The open knowledge actions `aidd list` shows: postmortem actions with a `target` of `pack:<slug>` or `skill:<name>`. For each one without a `tracked_in`, raise a suggested Spec (`suggested_by: agent:agile-coach`) for the project's own standards (config `standards:`), or a report upstream that `aidd upgrade` takes in. First search the declined Specs (`grep -rl 'decision: "declined"' <specs folder>`) for the same idea. If one is there, link the new Spec to it as `duplicates`, and quote its `triage.reason`. The suggested Spec is for a person to triage and an Approver to approve.
6. At most three new improvements, each with a metric, a target, and a check date. Each lesson takes the first form that fits, in the Learn order of the aidd skill (`references/observe-learn.md`). A mechanical mistake becomes a check: a test, a hook, a gate rule, or an eval scenario. A judgement becomes a `REVIEW.md` rule or a standard. An `AGENTS.md` line comes last. For a role, change at most one lever per cycle. Act only on a row with n above 10 whose move is outside the noise, and try a model-tier change before the role's text. No action is a valid result.

Show the author the retrospective, and stop. Humans choose which improvements to adopt. Each one then re-enters the loop at Plan as a new change, whose route the gate gives before the first edit (`aidd gate --paths`). The change is a Spec for this repository or the org preset, or an RFC for the method.
