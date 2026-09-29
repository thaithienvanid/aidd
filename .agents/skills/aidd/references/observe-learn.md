# Ship and Learn

Ship is merge, release, and observe: merged is not done. Release is whatever the repo's release interface does after merge (deploy, publish, flag rollout). Prefer progressive delivery: a feature flag or canary first, then full rollout.

## Observe

aidd 1.0.0 records the observe block and requires it where the profile says so; `aidd observe <spec> --write` runs the command at the start and the end of the window; your release tooling watches the signals in between.

Required on major, and on normal under the regulated profile. The Spec's `[observe]` block names:

- `window`: how long to watch, such as `30m`, `24h`, or `7d`
- `command`: a post-release check that exits 0 when healthy, and/or `signals`: the dashboards, SLOs, or queries a human watches
- `rollback_trigger`: the condition that starts the rollback, such as "5xx rate above 1% for 5 minutes"

One rule for who does what at Ship: you report; a person runs the rollback and records the outcome. When the trigger fires, report it at once with the evidence and the Spec's `rollback` steps; a person runs the rollback, sets status `rolled_back`, and Learn opens. When the window passes cleanly, report it; a person records `outcome.observe_result = "pass"` (`aidd observe <spec> --write`). When the Spec has a `hypothesis`, report `outcome.result` once its date arrives (met, missed, or inconclusive, with the number) for a person to record. A missed hypothesis is not a rollback; it is a Learn signal for the author, who decides whether to iterate, keep, or remove the change, consulting the product-manager.

An SLO's error budget is the natural rollback trigger and the natural freeze signal: a Policy command can answer `freeze` for feature routes while the budget is spent (the error budget policy of Google SRE), while the emergency route still passes and reliability work ships as normal changes.

## Learn

Learn runs after every reject at Merge approval, every rollback, every incident, and every Implement step that reached 3 retries, and on a cadence as a retrospective (see the operating loop's Learn step).

1. Write a short retro: what the agent misunderstood, which gate caught it, and which gate should have.
2. Turn the lesson into a change that makes the next run better. That can be a line in `AGENTS.md`, a new test, a path rule in `.aidd/config.toml`, or a clarified skill reference. It is itself a change and goes through the loop; most of these paths are protected, so it is major.
3. Record the link in the Spec's `outcome.learn_ref`.

For an incident, the retro is a postmortem: `aidd new postmortem <ID> --title "..." --spec <backfill Spec id>` writes `docs/postmortems/<ID>.md` (`assets/postmortem.md`), blameless, with action items that each have an owner and a due date. A procedure on-call follows is a runbook: `aidd new runbook <ID> --title "..."` writes `docs/runbooks/<ID>.md` (`assets/runbook.md`); record `last_tested` each time a person runs it, and `aidd doctor` warns once it is older than `runbook_max_age_days`.

**Every incident becomes a permanent check.** After an emergency or a rollback, the lesson is a regression test that reproduces the failure: it fails on the code that shipped and passes on the fix. When an agent's behavior caused it (a wrong route, an edit outside scope, a weakened test), add an eval scenario too, so the next model or prompt is graded on it. `outcome.learn_ref` links the test (and the scenario); a retro alone is not a lesson learned.

**The second-mistake rule.** When an agent makes the same mistake twice, the correction goes into `AGENTS.md` (or `CLAUDE.md`, where Claude Code reads it) as part of the fix, in the same PR: one line, written as the rule to follow ("run `make gen` after editing `schemas/`"), not as the story of what went wrong. The first time is a fix; the second time is a missing instruction.

**Keep the instruction file small.** `AGENTS.md` and `CLAUDE.md` load into every session, and a long one is read less carefully. Keep each under about one page: `aidd doctor` warns past 200 lines or 12 KiB. When a file grows past it, move detail into a skill or a doc it links, and delete lines that a test, a hook, or a gate rule now enforces, since the check outlasts the sentence.

## Metrics

The gate appends one JSON line per decision (`--events`). `aidd metrics events.jsonl` summarizes:

- final decisions and routes
- first-pass test rate
- how often a declared route was corrected
- top failing rules
- median changed lines
- the AI-assisted share
- the median wait per approval, the approvals and checks above `--target-wait`, and the median time from the first gate run to a pass: where changes wait longest is the constraint, and the retrospective improves that step first
- the open changes waiting, per approval (the human queue, which the WIP limit caps), and throughput in passing changes per week
- loop speed, each beside the quality metric it must not degrade: time to first feedback (with the first-pass test rate), approval wait p50 and p90 (with Spec rework after Spec approval), and flow efficiency (with the first-pass share); `first_feedback_minutes`, `approval_wait_p90_minutes`, and `flow_efficiency_min` in `[targets]` make `aidd metrics` exit 1 when missed

Pair them with your deploy data for the five DORA software delivery metrics: deployment frequency, change lead time, change fail rate, failed deployment recovery time, and deployment rework rate. `aidd metrics <events.jsonl> --dora` reports them against the `[targets]` in the config (add `--specs specs/` for the stability metrics from the Specs' `outcome`).
