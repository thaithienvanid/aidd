+++
aidd_version = "1.0.0"
kind = "postmortem"
id = "{{id}}"
title = "{{title}}"
incident_date = "{{today}}"
severity = "sev2"
spec = "{{spec}}"
owner_team = "{{owner_team}}"
status = "draft"
+++

<!-- Blameless: it names systems and decisions, never a person's fault. It finishes the emergency
     route's Learn step: the backfill Spec in `spec` records `outcome.learn_ref` pointing here, before
     its review_due (references/observe-learn.md). -->

## Summary

<!-- Three sentences: what broke, for whom, for how long, and what fixed it. -->

## Impact

<!-- Who was affected and how much: users, requests, revenue, data, and any commitment (SLO) missed. -->

## Timeline

<!-- UTC times, from the first bad signal to the all-clear: detection, each decision, the repair, recovery. -->

| Time (UTC) | Event |
| --- | --- |
| TODO | |

## Root cause

<!-- The technical cause, traced until the answer is a condition you can change, not a person. -->

## Contributing factors

<!-- What made it worse or slower to find: missing alerts, a stale runbook, an unclear owner. -->

## What went well

<!-- What to keep: the alert that fired, the runbook that worked, the rollback that was fast. -->

## Action items

<!-- Each item has one owner and a due date, and becomes a Spec or a ticket; none is "be more careful". -->

| Action | Owner | Due | Tracked in |
| --- | --- | --- | --- |
| TODO | | YYYY-MM-DD | |

## Lessons

<!-- What the team now knows that it did not, and which house standard or runbook changes because of it. -->
