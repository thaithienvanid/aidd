---
name: estimation
description: "Practice skill: estimate effort or cost as an honest range. Use when a proposal, an Initiative, a budget, or any plan a decision rests on needs a number, or when someone asks how long will this take, how much will it cost, give me an estimate, a quote, story points, a timeline, or is this doable by a date: three-point estimates, reference-class forecasting from comparable past work and the team's own `aidd metrics`, the assumptions behind the range, and what would narrow it."
metadata:
  checked: "2026-09-28"
---

# Estimation

**Use it when** a decision depends on how much work or money something takes: a proposal's price, an Initiative's budget, or the order of Epics.

**Do not use when** the work is one Spec the team can simply do: the loop measures it faster than an estimate predicts it.

## Standards

- Three-point estimation (PERT): low, most likely, and high for each part, combined as (low + 4 × likely + high) / 6 with the spread reported, not hidden.
- Reference-class forecasting (Flyvbjerg): start from how long comparable work actually took, then adjust for what is different, instead of building up from optimistic parts.
- The cone of uncertainty (McConnell, Software Estimation): the range is wide before discovery and narrows as needs are answered; say where on the cone the estimate sits.

## Estimate

- Break the work down only as far as the needs: one line per Epic-sized part, each with low, likely, and high.
- Take the reference class from the team's own record when it exists: `aidd metrics` gives lead times per route and type, and past proposals' estimates against actuals. Name the comparable work in `estimate.basis`.
- Add what agents do not do: human decisions and reviews, the addressee's own tasks, integration with systems you cannot see, and waiting.
- Report the range in `estimate` (`low`, `likely`, `high`, `unit`, `basis`), never one number, and the assumptions that would move it.

## Review

- The high end is plausible, not padded and not wishful; the basis names real comparable work; every assumption that moves the range is written down; nobody turned the range into a single price without a person deciding to.

## Hand off

- Done: `estimate` in the proposal or the Initiative, with its basis and assumptions. Next: the product manager and a person decide the price or the budget. Needs: commercial terms, margin, and any fixed price, which only a person sets. Stopped at: none, or the stop rule that fired.
