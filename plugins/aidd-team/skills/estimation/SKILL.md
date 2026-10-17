---
name: estimation
description: "Practice skill: estimate effort or cost as a range. Use in an aidd repository when a proposal, plan, or budget needs a number, or someone asks how long or how much."
metadata:
  checked: "2026-09-30"
---

# Estimation

**Use it when** a decision depends on how much work or money something takes: a proposal's price, an Initiative's budget, or the order of Epics.

**Do not use when** the work is one Spec the team can simply do: the loop measures it faster than an estimate predicts it.

## Standards

<!-- aidd:gen practice:estimation -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| Three-point estimation (PERT): low, most likely, and high per part, combined as (low + 4 x likely + high) / 6, with the spread reported | — | 2026-10-16 (reviewed) | — |
| Reference-class forecasting: start from how long comparable work actually took, then adjust for what differs | — | 2026-10-16 (reviewed) | — |
| The cone of uncertainty: a range is wide before discovery and narrows as needs are answered | — | 2026-10-16 (reviewed) | — |
| Monte Carlo forecasting from the team's own throughput: resample past weeks to answer 'when', and report percentiles, not a date | — | 2026-10-16 (reviewed) | — |
<!-- aidd:end -->

## Plan

- Break the work down only as far as the needs: one line per Epic-sized part. Give each line a low, likely, and high, combined as (low + 4 × likely + high) / 6. Report the spread, never hide it.
- Take the reference class from the team's own record when it exists. `aidd metrics --by route` gives each route's median hours from a change's first gate run to its first pass. For estimates against actuals, compare each past proposal's `estimate` with its milestones' `reached_on` dates. Start from how long comparable work took. Adjust for what differs. Name the comparable work in `estimate.basis`.
- For "when will these N items be done", forecast by Monte Carlo from the team's own throughput instead of summing estimates:
  1. Count the changes whose last gate decision passed, per week, in the gate events that `aidd metrics` reads. `aidd metrics` reports their weekly mean as `throughput_per_week`. Use at least ten weeks.
  2. Run 10,000 trials in a script with a fixed seed, so the result repeats. Each trial draws past weeks at random until N items are done.
  3. Report the 50th and 85th percentile finish weeks with the sample's dates.
- Fewer than ten weeks of record, or a change in team or scope since: say the forecast is weak.
- A date that assumes agents make the team faster stays inside the speed band: [references/speed-band.md](references/speed-band.md).
- Add what agents do not do: human decisions and reviews, the addressee's own tasks, integration with systems you cannot see, and waiting.
- Say where on the cone of uncertainty the estimate sits: wide before discovery, narrower as needs are answered.
- Report the range in `estimate` (`low`, `likely`, `high`, `unit`, `basis`), never one number, and the assumptions that would move it.
- Put the breakdown in `estimate.parts`, each part with its `kind`. `aidd validate` fails when their roll-up falls outside the range.

## Review

- The high end is plausible, not padded and not wishful. The basis names real comparable work. Every assumption that moves the range is written down. Nobody turned the range into a single price without a person deciding to.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Estimate range check | the estimate has low, likely, and high in order, a unit, and a basis | `aidd validate` on the proposal, which fails unless low <= likely <= high |
| Throughput forecast rerun | the Monte Carlo forecast is reproducible from its sample | the forecast script, run again with its fixed seed over the recorded weekly counts, prints the same 50th and 85th percentiles |

## Stop if

- The estimate is one number, or has no basis in comparable work.
- The range is about to become a price or a budget without a person deciding it.
- Human decisions, the addressee's tasks, or waiting are left out of the range.

## Hand off

- Done: `estimate` in the proposal or the Initiative, with its basis and assumptions. Next: the product manager and a person decide the price or the budget. Needs: commercial terms, margin, and any fixed price, which only a person sets. Stopped at: none, or the stop rule that fired.
