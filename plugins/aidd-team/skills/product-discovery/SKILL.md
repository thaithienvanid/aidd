---
name: product-discovery
description: "Practice skill: find and frame the problem before anything is built. Use when planning an Initiative or an Epic, slicing Specs, or judging whether a request deserves a change at all, or when someone says we need a feature, customers are asking for, what should we build next, prioritize the backlog, is this worth it, write user or job stories, or define acceptance criteria: outcomes and key results, customer interviews, an opportunity solution tree, assumption mapping, story mapping, job stories for backend work, EARS, prioritization, and a hypothesis the Spec carries to Learn."
metadata:
  checked: "2026-09-28"
---

# Product discovery

**Use it when** the team is about to plan or slice work, or when a request arrives fully formed as a solution. The cheapest change is the one nobody builds. Discovery is how the product manager justifies a smaller change, or none.

**Do not use when** the problem is already framed and the Spec exists; discovery is what happens before Specify, and re-opening it during Implement is how a frozen contract gets moved. Also not for a change whose outcome nobody intends to measure.

## Standards

- Jobs To Be Done (Christensen and Ulwick) for the outcome a customer hires the product for; job stories (Klement) for the situation, motivation, and outcome of a single job.
- EARS, the Easy Approach to Requirements Syntax (Mavin et al., 2009), as an optional pattern for Acceptance lines.
- OKRs for the measurable key results an Initiative names.
- The Mom Test (Fitzpatrick, 2013) for customer interviews: past behavior, specifics, and money or time spent, never opinions about the future.
- Opportunity solution trees (Torres, 2021) to keep opportunities, solutions, and experiments apart.
- Assumption mapping (Bland and Osterwalder, 2019) to test the riskiest assumption first.
- User story mapping (Patton, 2014) to slice by user activity.
- INVEST for the slices; the route budget is the size.
- Prioritization by cost of delay (WSJF, from SAFe) or by RICE (reach, impact, confidence, effort; Intercom, 2016).
- A positioning statement (Moore, 1991) and Amazon's PR/FAQ ("working backwards") when the change is a product rather than a feature.
- Lean Startup hypotheses (Ries, 2011): metric, baseline, expected move, and a date, so Learn can judge them.

## Plan, before an Initiative or an Epic

- Write the outcome as a job and a key result: who is better off, by how much, by when. If the request already names a solution, restate the problem behind it and check the smallest change that would serve it, including none.
- Read five to eight customer interviews, support tickets, or usage traces the author provides; ask for them when missing, and record what people did, not what they said they would do.
- Build the opportunity solution tree: the outcome at the root, the opportunities you heard, two or three candidate solutions per opportunity, and the experiment that would kill each one cheaply.
- Map the assumptions behind the chosen solution on importance and evidence; the riskiest, least-evidenced one becomes the first Spec's hypothesis or a spike.
- Rank with WSJF or RICE and say the reason in one line each; the order is the backlog.

## Specify, before Spec approval

- Slice with a story map: activities across, steps down, the first release as the thinnest walking skeleton; every slice is a Spec within its route budget, split by workflow step, business rule, data variation, or interface, never by technical layer.
- Give each Spec stub its acceptance intent (one to three Given/When/Then), its non-goals, and, when it should move a metric, its `hypothesis`.
- For infrastructure and backend work with no end user in sight, write job stories instead of user stories: *When* <situation>, *I want to* <motivation>, *so that* <outcome>. Each one also states idempotency (a second run changes nothing), failure and rollback with the real transaction boundaries (what is committed together, what is left if it stops halfway), and concurrency (two runs at once). Examples: [references/job-stories-and-ears.md](references/job-stories-and-ears.md).
- For the Spec's Acceptance, EARS is an optional way to make each line testable: "When <trigger>, the <system> shall <response>", plus its While, Where, and If-then forms (same reference).
- Write the Initiative map as a diagram (Initiative to Epics to Specs with `depends_on`), so a human sees the plan on one screen.
- A user-facing stub leaves the look open: the product designer offers two or three rough directions and a person picks one before any detailed prototype (`aidd-team:prototyping`).

## Proof, instead of test commands

- There is no test command for discovery; the proof is the hypothesis in the Spec and its `outcome.result` at Learn, read against the key result. `aidd metrics` shows throughput and wait; the key result shows value.

## Review and Learn

- At Learn, a missed hypothesis is a product decision (iterate, keep, or remove), never a rollback; a kept assumption goes back on the map with its new evidence.

## Hand off

- Done: the Initiative, the Epics, the ranked Spec stubs, and the map. Next: the architect, once a human agrees to the plan; then, for a user-facing stub, the product designer's rough directions for a person to pick from. Needs: the decision the plan waits for, or a customer fact you could not get. Stopped at: none, or the stop rule that fired.
