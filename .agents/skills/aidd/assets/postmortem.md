+++
aidd_version = "1.0.0"
kind = "postmortem"
id = "{{id}}"
title = "{{title}}"
incident_on = "{{today}}"
severity = "sev2"
spec = "{{spec}}"
owner_team = "{{owner_team}}"
status = "draft"
+++

<!-- Blameless: it names systems and decisions, never a person's fault. It finishes the emergency route's Learn step.
     The backfill Spec in `spec` records `outcome.learn_ref` pointing here, before its review_due
     (references/observe-learn.md).
     Write the prose at the `ste-80` level (the `aidd-team:plain-language` skill). -->

## Summary

<!-- Three sentences: what broke, for whom, for how long, and what fixed it. -->

## Impact

<!-- Who was affected and how much: users, requests, revenue, data, and any commitment (SLO) missed. -->

## Breach notification

<!-- Fill this in only when personal data was lost, disclosed, altered, or unavailable without authorization.
     Otherwise, write "no personal data involved" and why. Record when the team became aware: the clock starts there.
     Then record each notice. Under GDPR, they are:
     - the supervisory authority, within 72 hours of awareness where feasible (Art. 33)
     - the people affected, when the risk to them is high (Art. 34).
     Other regimes set other clocks and recipients (HIPAA, NIS2, state breach laws, contracts). A person decides and
     sends every notice. -->

| Recipient (authority, customers, people affected) | Regime and deadline | Sent (UTC) | Decided by |
| --- | --- | --- | --- |
| TODO | | | |

## Timeline

<!-- UTC times, from the first bad signal to the all-clear: detection, each decision, the repair, recovery. -->

| Time (UTC) | Event |
| --- | --- |
| TODO | |

## Trigger

<!-- The event that set it off (a deploy, a traffic spike, a certificate expiry). It is not the root cause: the trigger
     only exposed a weakness that was already there. -->

## Root cause

<!-- The technical cause, traced until the answer is a condition you can change, not a person. -->

## Detection

<!-- How it was found (an alert, a customer, a person noticing). Then the time to detect: from the first bad signal to
     the moment someone started working on it. What would have caught it sooner? -->

## Resolution

<!-- What stopped the impact (a rollback, a flag, a config change), who did it, and the time from detection to
     recovery. -->

## Contributing factors

<!-- What made it worse or slower to find: missing alerts, a stale runbook, an unclear owner. -->

## What went well

<!-- What to keep: the alert that fired, the runbook that worked, the rollback that was fast. -->

## Where we got lucky

<!-- What went right by chance and will not next time: the engineer who happened to be online, the quiet hour, the
     backup nobody had tested. Each is an action item. -->

## Action items

<!-- Each item has one owner and a due date, and becomes a Spec or a ticket. None is "be more careful". Record each
     one in the front matter too. `aidd validate` reads it there, and warns once its due date passes and it is not
     done. When the lesson belongs in the team's knowledge, add `target`: `pack:<slug>` or `skill:<name>`. Examples are
     a check a domain pack lacked, or a step a practice skill got wrong. `aidd validate` refuses an id the registry
     does not know. `aidd list` shows the action until it is done. The Learn step raises a suggested Spec that updates
     the pack or skill:

[[actions]]
what = "Alert on the checkout error rate"
owner = "@alice"
due = 2026-10-15
tracked_in = "SPEC-231"
done = false

[[actions]]
what = "Add a retry-storm check to the resilience skill"
owner = "@bob"
due = 2026-10-30
target = "skill:resilience"
-->

| Action | Owner | Due | Tracked in |
| --- | --- | --- | --- |
| TODO | | YYYY-MM-DD | |

## Lessons

<!-- What the team now knows that it did not, and which standard or runbook changes because of it. -->
