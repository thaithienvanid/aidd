---
name: retrospective
description: "Practice skill: run a retrospective on the delivery loop itself, from its numbers. Use in an aidd repository on the team's cadence, or after an incident, a rollback, or a rejected Merge approval."
metadata:
  checked: "2026-11-08"
---

# Retrospective

**Use it when** the team looks back at how the loop delivered: on its cadence (`limits.retrospective_every`), or after a Learn signal (`/aidd-team:retro`).

**Do not use when** one incident needs its blameless postmortem (`/aidd-team:postmortem`), or one bug needs its cause (`aidd-team:debugging`).

## Standards

<!-- aidd:gen practice:retrospective -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| Inspect and adapt: the retrospective on the loop itself | — | 2026-10-16 | — |
| Retrospective action items are tracked to closure and reviewed at the next retro, because an untracked action item is a decision not to change | — | 2026-10-16 | — |
| Flow metrics for a team of agents and humans: flow velocity, flow efficiency, cycle-time percentiles, cumulative flow, and the blocked-stall ratio | — | 2026-10-16 | <https://flowframework.org/> |
| Kanban flow for agent teams: WIP limits on human decisions, pull, classes of service, and flow metrics (lead time, throughput, wait time, open changes waiting) | The Kanban Guide 2025.5 | 2026-10-16 | <https://kanbanguides.org/the-kanban-guide/2025.5/> |
| Theory of Constraints (improve the bottleneck first) | — | 2026-10-16 | — |
| Five Whys and A3 problem solving | — | 2026-10-16 | — |
| Psychological safety as the precondition for a blameless retrospective; without it the retro produces silence, not signal | — | 2026-10-16 | — |
| Agent-team operations: WIP limits on human decisions and never on agents, a review queue sized to what a person can decide today, and token and model cost governed like any other budget (emerging) | DORA AI Capabilities Model, 2025 | 2026-10-16 | <https://dora.dev/ai/capabilities-model/report/> |
<!-- aidd:end -->

## Learn

- **Evidence first.** Read the changes merged since the last retrospective, from `git log` and the merged PR/MRs: the lead time and the DORA metrics. Read the postmortems, the `outcome` fields, the review findings, and the rejections since then. Numbers, never impressions.
- **Last cycle first.** Keep, adjust, or revert each improvement you adopted, on its metric and its check date, in `docs/retros/improvement-log.md`.
- **Find the constraint.** Look where changes wait longest or loop back most. Look at the human queue first: the wait for a person's yes. A WIP limit applies to the people who decide, never to agents. Ask why until you reach a cause in the system, never a person.
- **Pair every speed metric with a quality one.** A metric that became a target stops measuring: a lead time that fell while the change fail rate rose is a gamed number, not a better loop. Never rank people.
- **At most three improvements**, each with a metric, a target, and a check date. Take the first form that fits. A mechanical mistake becomes a check: a test, a lint rule, a CI check, or an eval case. A judgement becomes a `REVIEW.md` rule or a standard, and an `AGENTS.md` line comes last. A change to the method is an RFC draft in `docs/rfcs/`. For a role, change one lever a cycle, only past n=10 and outside the noise, and try its model tier before its text. No action is a valid result.
- **Tighten freely, loosen with evidence.** A change that loosens a control needs its numbers, and goes through the loop like any other.
- **Write it up** in `docs/retros/YYYY-MM-DD.md`. A finding class that repeats across review reports gets a proposed rule or lint in the improvement log.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Improvement check | each improvement names a metric, a target, and a check date | read `docs/retros/improvement-log.md`: every open row has the three, and every row past its date is kept, adjusted, or reverted |
| Metric pair check | no speed metric stands alone | each lead-time or throughput number in the retrospective sits beside a change fail rate, rollback, or review number for the same period |

## Stop if

- An improvement would loosen a control without evidence, or change a risk rule, the config, a role, or an agent file. It goes through the loop, and a person decides.
- A number rests on fewer than ten changes, or its move sits inside the noise.
- A finding names a person as the cause.

## Hand off

- Done: the retrospective in `docs/retros/`, and each change to the method as an RFC draft in `docs/rfcs/`. Each improvement that needs a Spec is in the return file the lead names, for the product manager to draft. Next role: the product manager; then a person chooses which to adopt, and each re-enters the loop at Plan. Needs: that choice. Stopped at: none, or the stop rule's code.
