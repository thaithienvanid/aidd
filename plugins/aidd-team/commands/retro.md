---
description: "Run a retrospective on the AIDD loop itself with the agile coach, and propose measured improvements"
argument-hint: "[since date, such as 2026-09-11]"
---

Loop step: **Learn**, on a cadence (every two weeks or 20 merged changes) and after every Learn signal.

Lanes: fast, spec, emergency.

Run the `aidd-team:agile-coach` subagent for the period since $ARGUMENTS (default: the last file in `docs/retros/`):

1. `aidd metrics <events.jsonl> --since <last retrospective>` on the gate events.
2. The postmortems and review findings since then.
3. Last cycle's improvements kept or reverted on their numbers.
4. `aidd eval standards` for every role or domain standard nobody re-checked within a year.
5. At most three new improvements, each with a metric, a target, and a check date.

Show the author the retrospective, and stop. Humans choose which improvements to adopt; each one then re-enters the loop at Plan as a new change, which starts with `aidd next`: a Spec for this repository or the org preset, or as an RFC for the method.
