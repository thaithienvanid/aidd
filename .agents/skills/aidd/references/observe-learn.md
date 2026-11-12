# Roll out and Learn

Roll out is release and observe, after the change is merged: merged is not done. Release is whatever the repository's release tooling does next (a deploy, a package, a flag rollout). A deploy or a release you run yourself is `deploy.run` or `release.publish`, so ask. Prefer progressive delivery: a feature flag or canary first, then full rollout. Release notes start from `assets/release-notes.md`.

## Observe

The Spec's `observe` block names:

- `window`: how long to watch, such as `30m`, `24h`, or `7d`
- `command`: a post-release check that exits 0 when healthy, and/or `signals`: the dashboards, SLOs, or queries a person watches
- `rollback_trigger`: the condition that starts the rollback, such as "5xx rate above 1% for 5 minutes"

The SRE runs the Spec's observe command over the window, and records `outcome.observe_result` from its exit code: pass or fail. With no observe command, a person watches the signals. When the trigger fires, report it at once, with the evidence and the Spec's `rollback` steps, and ask before you run them (`deploy.run`). Learn opens after the rollback. When the window passes cleanly, report it.

When the Spec has a `hypothesis`, report its result once its date arrives (met, missed, or inconclusive, with the number). Never run a runbook's steps against a live system without the person's yes: each one that changes it is an `ask` action. Each `outcome` field has one source (`references/state.md`, What you record). A missed hypothesis is not a rollback, but a Learn signal for the author. The author consults the product manager, and decides whether to iterate, keep, or remove the change.

An SLO's error budget is the natural rollback trigger. While the budget is spent, the team ships reliability work first, the error budget policy of Google SRE.

## Learn

Learn runs after every rejected Merge approval, rollback, incident, and Task out of retries, and on a cadence as a retrospective. Product feedback goes in a feedback log (`assets/feedback.md`), which needs no Spec.

1. Write a short retro: what the agent misunderstood, which check caught it, and which check should have.
2. Turn the lesson into a change that makes the next run better. Take the first form that fits, since a check outlasts a sentence:
   1. A mechanical mistake (a wrong route, a skipped command, an edit outside the scope) becomes a check: a test, an area or a rule in `.aidd/config.yaml` `risks`, or an eval scenario.
   2. A judgement (a design, a name, what to test) becomes a rule in `REVIEW.md`, or a standard in a skill or a domain pack.
   3. Only when neither fits, it becomes one line in `AGENTS.md`.

   That change goes through the loop too. Most of these paths are in the `agent_config` area, so the route is at least normal.
3. Record the link in the Spec's `outcome.learn_ref`.

**The cadence.** Every 14 days or 20 merged changes, or as `limits.retrospective_every` sets, run a retrospective on the loop itself. Use the git log since the last one, the Specs' `outcome` fields, the postmortems, and the review findings. Keep or revert last cycle's improvements on their numbers. Then propose at most three new ones, each with a metric, a target, and a check date. Each re-enters Plan as a new change: a Spec (this repository or the org preset), an RFC (the method), or a test (an escaped defect). Check its route before the first edit (`aidd risk --paths`). You propose; a person decides. A proposal that lowers a rule cites the metric that justifies it.

For an incident, the retro is a postmortem. `aidd new postmortem <ID> --title "..." --spec <backfill Spec id>` writes `docs/postmortems/<ID>.md` (`assets/postmortem.md`). The postmortem is blameless, and each action item has an owner and a due date. An action whose lesson belongs in a domain pack or a practice skill carries `target: pack:<slug>` or `"skill:<name>"`. `aidd status` shows it until it is done. You raise a suggested Spec that updates that pack or skill.

A procedure on-call follows is a runbook. `aidd new runbook <ID> --title "..."` writes `docs/runbooks/<ID>.md` (`assets/runbook.md`). Record `tested_on` each time a person runs the runbook. `aidd doctor` warns once it is older than `docs.max_runbook_age_days`. A living doc (the glossary, the data map) may record `reviewed_on` in `---` front matter in the same way. `aidd doctor` warns once it is older than `docs.max_review_age_days`.

**Every incident becomes a permanent check.** After an emergency or a rollback, the lesson is a regression test that reproduces the failure. The test fails on the code that was merged, and passes on the fix. When an agent's behavior caused the failure (a wrong route, an edit outside scope, a weakened test), add an eval scenario too. The scenario then grades the next model or prompt. `outcome.learn_ref` links the test (and the scenario). A retro alone is not a lesson learned.

**The second-mistake rule.** When an agent makes the same mistake twice, add the correction as part of the fix, in the same PR, in the order of step 2: a check, then a `REVIEW.md` rule or a standard. Add a line to `AGENTS.md`, which `CLAUDE.md` imports, only when neither fits. Write the line as the rule to follow ("run `make gen` after editing `schemas/`"), not as the story of what went wrong. The first time is a fix; the second time is a missing check.

**Keep the instruction file small.** `AGENTS.md` and `CLAUDE.md` load into every session, and an agent reads a long one less carefully. Keep each under about one page: `aidd doctor` warns past 200 lines or 12 KiB. Each time you add a line, delete one that a test or a risk rule now covers, since the check outlasts the sentence. When a file grows past the limit, move detail into a skill or a doc it links.

**Delivery metrics.** Pair the git log with your deploy data for the five DORA software delivery metrics: deployment frequency, change lead time, change fail rate, failed deployment recovery time, and deployment rework rate. The Specs' `outcome` fields give the stability ones.
