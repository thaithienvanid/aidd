# Ship and Learn

Ship is merge, release, and observe: merged is not done. Release is whatever the repo's release interface does after merge (deploy, publish, flag rollout). Prefer progressive delivery: a feature flag or canary first, then full rollout. Release notes start from `aidd release-notes` and `assets/release-notes.md`.

## Observe

aidd records the observe block and requires it where the profile says so: on major, and on normal under the regulated profile. `aidd observe <spec>` runs the observe command once. With `--window`, it runs the command again and again until the window ends, and it stops when the rollback trigger fires. `--write` records the result. With no observe command, a person watches the signals.

The Spec's `[observe]` block names:

- `window`: how long to watch, such as `30m`, `24h`, or `7d`
- `command`: a post-release check that exits 0 when healthy, and/or `signals`: the dashboards, SLOs, or queries a human watches
- `rollback_trigger`: the condition that starts the rollback, such as "5xx rate above 1% for 5 minutes"

One rule for who does what at Ship: you report, and a person runs the rollback and records the outcome. When the trigger fires, report it at once, with the evidence and the Spec's `rollback` steps. Learn opens after the rollback. When the window passes cleanly, report it.

When the Spec has a `hypothesis`, report its result once its date arrives (met, missed, or inconclusive, with the number). You never run a runbook's steps against a live system: you propose them, and a person runs them. Each `outcome` field has one owner (`references/state.md`, What you record). A missed hypothesis is not a rollback, but a Learn signal for the author. The author consults the product-manager, and decides whether to iterate, keep, or remove the change.

An SLO's error budget is the natural rollback trigger and the natural freeze signal. While the budget is spent, a Policy command can answer `freeze` for feature routes (the error budget policy of Google SRE). Then the emergency route still passes, and reliability work ships as normal changes.

## Learn

Learn runs after every reject at Merge approval, rollback, incident, and Implement step that reached 3 retries, and on a cadence as a retrospective. Product feedback goes in a feedback log (`assets/feedback.md`), which needs no Spec.

1. Write a short retro: what the agent misunderstood, which gate caught it, and which gate should have.
2. Turn the lesson into a change that makes the next run better. Take the first form that fits, since a check outlasts a sentence:
   1. A mechanical mistake (a wrong route, a skipped command, an edit outside the scope) becomes a check: a test, a hook, a gate or path rule in `.aidd/config.toml`, or an eval scenario.
   2. A judgement (a design, a name, what to test) becomes a rule in `REVIEW.md`, or a standard in a skill or a domain pack.
   3. Only when neither fits, it becomes one line in `AGENTS.md`.

   That change goes through the loop too. Most of these paths are protected, so it is major.
3. Record the link in the Spec's `outcome.learn_ref`.

**The cadence.** Every two weeks or 20 merged changes, run a retrospective on the loop itself. Use `aidd metrics <events.jsonl> --since <last retrospective>`, the postmortems, and the review findings. Keep or revert last cycle's improvements on their numbers. Then propose at most three new ones, each with a metric, a target, and a check date. Each re-enters Plan as a new change: a Spec (this repository or the org preset), an RFC (the method), or a test (an escaped defect). `aidd assess` checks its route before the first edit. You propose; you never adopt. Process files are protected paths, so a person decides. A proposal that loosens a control cites the metric that justifies it.

For an incident, the retro is a postmortem. `aidd new postmortem <ID> --title "..." --spec <backfill Spec id>` writes `docs/postmortems/<ID>.md` (`assets/postmortem.md`). The postmortem is blameless, and each action item has an owner and a due date. An action whose lesson belongs in a domain pack or a practice skill carries `target = "pack:<slug>"` or `"skill:<name>"`. `aidd list` shows it until it is done. You raise a suggested Spec that updates that pack or skill.

A procedure on-call follows is a runbook. `aidd new runbook <ID> --title "..."` writes `docs/runbooks/<ID>.md` (`assets/runbook.md`). Record `tested_on` each time a person runs the runbook. `aidd doctor` warns once it is older than `runbook_max_age_days`. A living doc (the glossary, the data map, an SLO) may record `reviewed_on` in `+++` front matter in the same way. `aidd doctor` warns once it is older than `[docs] max_review_age_days`.

**Every incident becomes a permanent check.** After an emergency or a rollback, the lesson is a regression test that reproduces the failure. The test fails on the code that shipped, and passes on the fix. When an agent's behavior caused the failure (a wrong route, an edit outside scope, a weakened test), add an eval scenario too. The scenario then grades the next model or prompt. `outcome.learn_ref` links the test (and the scenario). A retro alone is not a lesson learned.

**The second-mistake rule.** When an agent makes the same mistake twice, add the correction as part of the fix, in the same PR, in the order of step 2: a check, then a `REVIEW.md` rule or a standard. Add a line to `AGENTS.md` (or `CLAUDE.md`, where Claude Code reads it) only when neither fits. Write the line as the rule to follow ("run `make gen` after editing `schemas/`"), not as the story of what went wrong. The first time is a fix; the second time is a missing check.

**Keep the instruction file small.** `AGENTS.md` and `CLAUDE.md` load into every session, and an agent reads a long one less carefully. Keep each under about one page: `aidd doctor` warns past 200 lines or 12 KiB. When a file grows past the limit:

- move detail into a skill or a doc it links
- delete lines that a test, a hook, or a gate rule now enforces, since the check outlasts the sentence

## Metrics

The gate appends one JSON line per decision (`--events`). `aidd metrics events.jsonl` summarizes:

- final decisions and routes
- first-pass test rate
- how often a declared route was corrected
- top failing rules
- median changed lines
- the AI-assisted share
- the median wait per approval, the approvals and checks above `--target-wait`, and the median time from the first gate run to a pass. Where changes wait longest is the constraint: the retrospective improves that step first.
- the open changes waiting, per approval (the human queue, which the WIP limit caps), and throughput in passing changes per week
- loop speed, each beside the quality metric it must not degrade:
  - time to first feedback, with the first-pass test rate
  - approval wait p50 and p90, with Spec rework after Spec approval
  - flow efficiency, with the first-pass share

`max_first_feedback_minutes`, `max_approval_wait_p90_minutes`, and `min_flow_efficiency` in `[targets]` make `aidd metrics` exit 1 when missed.

Pair them with your deploy data for the five DORA software delivery metrics. These are deployment frequency, change lead time, change fail rate, failed deployment recovery time, and deployment rework rate. `aidd metrics <events.jsonl> --dora` reports them against the `[targets]` in the config (add `--specs specs/` for the stability metrics from the Specs' `outcome`).
