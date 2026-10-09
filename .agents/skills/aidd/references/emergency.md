# The emergency lane

Read this when the author declares a production repair (route `emergency`). The lane is Implement ⟲ Verify → Review → Ship → Learn, and it may ship under a freeze.

The repair is Implement, its smoke tests the Verify step. Ship needs the route's approvals, the named commander's approval, and a specialist approval when a protected path changes. The commander is a human in `owners.approvers`, not an author.

The inline Change Request block names `severity`, `kind`, `commander`, `review_due`, and `backfill`. `review_due` is within `emergency.review_sla_days` (default 2) of the day the change opened or its head was last pushed, whichever is later. Commit the `backfill` stub, with the same `review_due`, in the same change (`aidd new spec INC-<n> --title "<incident>" --route emergency`).

After the release, by `review_due`:

- Finish the backfill Spec and run the review.
- Write the regression test that reproduces the incident, and an eval scenario when an agent's behavior caused it. Record its link in `outcome.learn_ref`.

`aidd validate` fails once this work is overdue. The postmortem and its action items: `references/observe-learn.md`.

If the incident may involve personal data, the breach-notification clock starts when the team becomes aware of it, not when the repair ships. Under GDPR, the controller notifies the supervisory authority without undue delay and, where feasible, within 72 hours (Art. 33). It also notifies the people affected when the risk to them is high (Art. 34). Other regimes set other clocks and recipients; the incident runbook names the ones that apply. A person decides and sends every notice. Record the time of awareness in the incident timeline, and later in the postmortem.

Stops: `SKILL.md` stop 3 (no commander, or the commander would be you or the author).
