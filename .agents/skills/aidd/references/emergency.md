# The emergency route

Read this when the author declares a production repair (route `emergency`). The steps are Implement ⟲ Verify → Review → ask: Merge approval → Merge → Roll out → the backfill Spec → Learn. Repair production first, and write the Spec after.

The repair is Implement, and its smoke tests are the Verify step. Keep it to the fewest lines that restore service. The asks still hold: ask for Merge approval, and ask before the deploy (`deploy.run`). Say what the repair does and how to undo it in each question, so the person can answer fast.

Commit a backfill Spec in the same change: run `aidd new spec INC-<n> --title "<incident>" --route emergency`. It writes the `emergency` block with a `backfill_due` two days out. Fill in the block (`references/spec-release.md`).

After the release, by `backfill_due`:

- Finish the backfill Spec and run the post-incident review. The code review came before the merge.
- Write the regression test that reproduces the incident, and an eval scenario when an agent's behavior caused it. Record its link in `outcome.learn_ref`.

The postmortem and its action items: `references/observe-learn.md`.

If the incident may involve personal data, the breach-notification clock starts when the team becomes aware of it, not when the repair lands. Under GDPR, the controller notifies the supervisory authority without undue delay and, where feasible, within 72 hours (Art. 33). It also notifies the people affected when the risk to them is high (Art. 34). Other regimes set other clocks and recipients, and the incident runbook names the ones that apply. A person decides and sends every notice (`message.send`). Record the time of awareness in the incident timeline, and later in the postmortem.
