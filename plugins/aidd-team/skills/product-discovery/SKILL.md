---
name: product-discovery
description: "Practice skill: frame the problem before building. Use in an aidd repository when planning an Initiative or Epic, slicing Specs, or judging whether a request is worth doing."
metadata:
  checked: "2026-09-30"
---

# Product discovery

**Use it when** the team is about to plan or slice work, or a request arrives as a ready-made solution. The cheapest change is the one nobody builds. Discovery is how the product manager justifies a smaller change, or none.

**Do not use when** nobody intends to measure the change's outcome, or the problem is framed and the Spec exists. Re-opening discovery during Implement moves a frozen contract.

## Standards

<!-- aidd:gen practice:product-discovery -->
| Standard | Edition |
| --- | --- |
| Jobs To Be Done | — |
| OKRs for outcomes | — |
| Opportunity solution trees and assumption mapping for discovery; user story mapping for slicing | — |
| Slicing over estimation: INVEST Small means within the route budget, and forecasts come from lead time and throughput, not story points | — |
| WSJF or MoSCoW prioritization | — |
| Product analytics: a measurable key result per Epic, with pre-registered metrics for A/B tests | — |
| EARS, the Easy Approach to Requirements Syntax, as an optional pattern for Acceptance lines | — |

Each standard's checked date and source are in the aidd-team roles reference (`references/roles.md` in `aidd-team:aidd-team`), section `aidd-team:product-discovery`.
<!-- aidd:end -->

## Plan

1. Write the outcome as a job and a key result: who is better off, by how much, by when. If the request names a solution, restate the problem behind it and check the smallest change that serves it, including none. For a product, not a feature, add a positioning statement and a PR/FAQ ("working backwards").
2. Read five to eight interviews, support tickets, or usage traces the author provides (ask when missing). Record what people did, not what they said they would do (past behaviour, specifics, money or time spent).
3. Build the opportunity solution tree: the outcome at the root, the opportunities heard, two or three candidate solutions each, and the cheap experiment that would kill each.
4. Map the chosen solution's assumptions on importance and evidence. The riskiest, least-evidenced one becomes the first Spec's hypothesis or a spike ([references/spikes.md](references/spikes.md)).
5. Rank with WSJF or RICE, one line of reason each. The order is the backlog. Draw the Initiative map (Initiative to Epics to Specs, with `depends_on`).

## Specify

- Slice with a story map: activities across, steps down, the first release the thinnest walking skeleton. Each slice is a Spec within its route budget (INVEST). Split by workflow step, business rule, data variation, or interface, never by technical layer.
- Give each Spec stub its acceptance intent (one to three Given/When/Then), its non-goals, and, when it should move a metric, its `hypothesis`: metric, baseline, expected move, date.
- For infrastructure and backend work with no end user, write job stories: *When* <situation>, *I want to* <motivation>, *so that* <outcome>. Each states idempotency (a second run changes nothing), failure and rollback at the real transaction boundaries, and concurrency (two runs at once). EARS ("When <trigger>, the <system> shall <response>") optionally makes an Acceptance line testable. Examples: [references/job-stories-and-ears.md](references/job-stories-and-ears.md).
- A user-facing stub leaves the look open. The product designer offers two or three rough directions. A person picks one before any detailed prototype (`aidd-team:prototyping`).

## Learn

- A missed hypothesis is a product decision (iterate, keep, or remove), never a rollback. A kept assumption returns to the map with its new evidence.
- Read the feedback log (`docs/feedback/`, from `aidd new feedback`) and `aidd digest`'s theme counts. A recurring theme with no linked Spec is a candidate stub. Record each theme's decision in the log.

## Test commands

Discovery has no test command: the proof is the Spec's hypothesis and its `outcome.result` at Learn, read against the key result. `aidd metrics` shows throughput and wait; the key result shows value.

## Stop if

- The request names a solution and nobody has written the problem behind it.
- A slice is cut by technical layer, or exceeds its route budget.
- A hypothesis has no metric, baseline, expected move, or date.
- You are about to pick a user-facing direction for the person.

## Hand off

- Done: the Initiative, the Epics, the ranked Spec stubs, and the map. Next: the architect, once a human agrees to the plan; for a user-facing stub, then the product designer's rough directions for a person to pick. Needs: the decision the plan waits for, or a customer fact you could not get. Stopped at: none, or the stop rule that fired.
