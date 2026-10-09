---
description: "Run a retrospective on the AIDD loop itself with the agile coach, and propose measured improvements"
disable-model-invocation: true
argument-hint: "[since date, such as 2026-09-11]"
---

Loop step: **Learn**, on a cadence (every two weeks or 20 merged changes) and after every Learn signal.

Lanes: fast, spec, emergency.

<!-- aidd:gen roles:lead -->
**You are the lead.** You run this command and the roles do its work:

1. You route; you never edit an artifact yourself. Send a change to a Spec, a test, a proposal, or code to the role that owns the file. Pass on that role's handoff note.
2. Hand over file paths, not pasted facts: "read specs/SPEC-1.md and its latest handoff note", never a restatement of what a file already says.
3. Launch the roles of one group in parallel, in one message, and wait for all of them before you act. Do not take a turn per completion.
4. Pass the `model` in every Agent call: the one the role's agent file names, which follows its tier (`opus` for reasoning, `sonnet` for execution). Read-only search helpers (Explore) take the execution tier's model.
5. Start each command in a fresh session (or after `/clear`). It begins from the files and the latest handoff note, never from an earlier command's conversation.
6. A revision changes each affected section with one Edit (Write only a new or mostly rewritten file). It reruns only the roles whose part the new facts change.
7. End with the handoff note, its Spend line included, and stop where the command stops.
<!-- aidd:end -->

Run the `aidd-team:agile-coach` subagent for the period since $ARGUMENTS (default: the last file in `docs/retros/`):

1. `aidd metrics <events.jsonl> --since <last retrospective>` on the gate events.
2. The postmortems, review findings, the feedback log (`aidd digest` counts its themes), and the support the delivery manager reported against the contract's levels, since then.
3. Last cycle's improvements kept or reverted on their numbers.
4. `aidd eval standards` for every role or domain standard past its review cadence or its `review_due`. Also read the latest `aidd eval standards --online` report (the weekly standards check's job summary) for quotes moved or missing.
5. The open knowledge actions `aidd list` shows: postmortem actions with a `target` of `pack:<slug>` or `skill:<name>`. For each one without a `tracked_in`, raise a suggested Spec (`suggested_by = "agent:agile-coach"`) that updates that pack or skill. First search the declined Specs (`grep -rl 'decision = "declined"' <specs folder>`) for the same idea. If one is there, link the new Spec to it as `duplicates`, and quote its `triage.reason`. The suggested Spec is for a person to triage and its steward to review.
6. At most three new improvements, each with a metric, a target, and a check date. Each lesson takes the first form that fits, in the Learn order of the aidd skill (`references/observe-learn.md`). A mechanical mistake becomes a check: a test, a hook, a gate rule, or an eval scenario. A judgement becomes a `REVIEW.md` rule or a standard. An `AGENTS.md` line comes last.

Show the author the retrospective, and stop. Humans choose which improvements to adopt. Each one then re-enters the loop at Plan as a new change, whose route `aidd assess` checks before the first edit. The change is a Spec for this repository or the org preset, or an RFC for the method.
