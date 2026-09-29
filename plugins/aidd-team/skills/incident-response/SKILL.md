---
name: incident-response
description: "Practice skill: run the live phase of an incident, from the first alert until service is restored and the backfill is handed over. Use when production is down or degraded, an alert is firing, users report errors or outages, data looks wrong or lost, a deploy went bad, a security breach or a leaked credential is suspected, or someone says it is down, we are on fire, sev1, page someone, roll it back, or is this an incident: declare it and name a human commander, mitigate before diagnosing, keep a timeline, update a named audience on a cadence, preserve evidence, and hand off to the postmortem and the emergency lane's backfill Spec."
metadata:
  checked: "2026-09-28"
---

# Incident response

**Use it when** users are hurt now or will be within the hour: an outage, a degradation past the SLO, wrong or lost data, a bad deploy, or a suspected security breach. It covers the live phase only.

**Do not use when** the service is healthy and you are finding a bug's cause (`aidd-team:debugging`), or the incident is over and the work is learning from it (`/aidd-team:postmortem`). An agent never commands an incident and never decides to stop one; a person does.

## Standards

- Google SRE book, chapter 14, "Managing Incidents": a declared incident, separate roles (incident commander, operations, communications, planning), a living incident document, and a clear handoff.
- NIST SP 800-61 Rev. 3 (April 2025) for security incidents: incident response as part of CSF 2.0 risk management, with evidence handling and reporting duties.

## Declare

- Declare early; an incident closed as a false alarm costs little, an undeclared one costs a lot. Give it a name and a severity using the project's scale.
- A human is the incident commander, named in the incident channel and later in the emergency change's `commander`. The agent assists the commander: it proposes, gathers, and drafts; it does not decide.
- Open one incident document: the commander, who is doing what, the current state, the timeline, and the next update time.

## Mitigate before diagnosing

- Stop the harm first, then find the cause. Rolling back the last change is the first option when the timing fits: a release, a flag flip, a configuration push, or a migration just before the symptom.
- Other mitigations, cheapest and most reversible first: turn off a flag, drain or shift traffic, scale up, shed load, block an abusive client, rotate a leaked credential, pause a job that is corrupting data.
- Every action goes through the commander and into the timeline before it runs; one change at a time, so you know which one helped.
- A code repair on the emergency lane opens a change with the inline block (`severity`, `kind`, `commander`, `review_due`, `backfill`) and commits the backfill stub, `aidd new spec INC-<n> --title "<incident>" --route emergency`, in the same change.

## Keep the record

- The timeline, in UTC, with who did what and what was seen: alerts, graphs, decisions, commands run, and their effect. Write it as you go; memory rewrites it by tomorrow.
- Preserve evidence before it expires or is overwritten: logs, traces, dashboards as images, the deployed version, the configuration, and for a security incident, disk and memory images and access logs, untouched and with a note of who handled them. Never "clean up" a compromised host before the security engineer says so.

## Communicate

- Name the audience (internal responders, support, leadership, customers, regulators where the law requires notice) and a cadence per audience, such as every 30 minutes for responders while severity is high. Say when the next update comes, and keep that promise even when there is no news.
- Each update states impact, what is being done, and the next update time; no guessed cause presented as fact. Templates: [references/updates.md](references/updates.md).

## Test commands

- During the incident, the checks are the SLI and the smoke tests that show service restored; after it, the regression test that reproduces the incident, in the backfill Spec, linked from `outcome.learn_ref`.

## Hand off

- Done: service restored, the timeline, the evidence list, and the emergency change with its backfill stub. Next: the commander declares the end; `/aidd-team:postmortem specs/INC-<n>.md` writes the blameless postmortem and finishes the backfill Spec by `review_due`. Needs: the commander's decisions, and a person for any customer or regulator notice. Stopped at: none, or the stop rule that fired.

## Stop if

- No human commander is named, or you are about to take an action the commander has not agreed to.
- You are diagnosing while a known rollback or mitigation is waiting.
- Evidence is about to be overwritten, rotated, or deleted.
- An update is overdue, or a cause is being announced before it is confirmed.
