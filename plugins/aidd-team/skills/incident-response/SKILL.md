---
name: incident-response
description: "Practice skill: run a live incident until service is back. Use in an aidd repository when production is down or degraded, an alert fires, or a breach is suspected."
metadata:
  checked: "2026-10-22"
---

# Incident response

**Use it when** users are hurt now or will be within the hour: an outage, degradation past the SLO, wrong or lost data, a bad deploy, or a suspected breach. It covers only the live phase, and owns the breach notification clocks every pack points to.

**Do not use when** the service is healthy and you are finding a bug's cause (`aidd-team:debugging`), or the incident is over and you are learning from it (`/aidd-team:postmortem`). An agent never commands or ends an incident. A person does.

## Standards

<!-- aidd:gen practice:incident-response -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| Managing incidents: declared, with separate roles (commander, operations, communications, planning), a living incident document, and a clear handoff | — | 2026-10-16 (reviewed) | <https://sre.google/sre-book/managing-incidents/> |
| NIST SP 800-61, incident response as a CSF 2.0 Community Profile, with evidence handling and reporting duties | SP 800-61 Rev. 3 | 2026-10-16 | <https://csrc.nist.gov/pubs/sp/800/61/r3/final> |
| GDPR Art. 33 and 34 (personal-data breach notification) | Regulation (EU) 2016/679 | 2026-10-16 | <https://eur-lex.europa.eu/eli/reg/2016/679/oj> |
| NIS2 Directive: significant-incident reporting by essential and important entities (Article 23) | Directive (EU) 2022/2555 | 2026-10-16 | <https://eur-lex.europa.eu/eli/dir/2022/2555/oj> |
| EU Cyber Resilience Act for products with digital elements | Regulation (EU) 2024/2847 | 2026-10-22 | <https://digital-strategy.ec.europa.eu/en/policies/cyber-resilience-act> |
| EU Digital Operational Resilience Act | Regulation (EU) 2022/2554 | 2026-10-16 | <https://eur-lex.europa.eu/eli/reg/2022/2554/oj> |
| HIPAA Breach Notification Rule (45 CFR 164.400 to 164.414) | 45 CFR Parts 160 and 164; 42 CFR Part 2; 16 CFR Part 318 | 2026-10-16 | <https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C> |
| SEC cybersecurity incident disclosure: Form 8-K Item 1.05 for a material incident | SEC final rule of 2023-07-26 | 2026-10-16 | <https://www.sec.gov/newsroom/press-releases/2023-139> |
<!-- aidd:end -->

## Roll out

### Declare

- Declare early, with a name and severity. A human is the incident commander, named in the channel and the emergency change's `commander`. The agent proposes, gathers, and drafts, never decides. One incident document: commander, who does what, state, timeline, next update.
- The commander hands off out loud, "you are now the commander", and the timeline records it. Other deploys to the affected service wait until the commander ends the incident.

### Mitigate before diagnosing

- Stop the harm first: roll back the last change (release, flag, config, migration) when the timing fits. Else, take the cheapest and most reversible action first: a flag off, traffic shifted, scale up, shed load, block a client, rotate a leaked credential, pause a job corrupting data.
- Each action goes through the commander and into the timeline before it runs, one at a time. A code repair on the emergency lane opens a change with the inline Change Request block (`severity`, `kind`, `commander`, `review_due`, `backfill`) and commits the backfill stub, `aidd new spec INC-<n> --title "<incident>" --route emergency`.

### Keep the record

- Write the timeline in UTC as you go: who did what, what was seen, what changed.
- Preserve evidence before it expires: logs, traces, dashboards, the deployed version, the config. For a security incident, add untouched disk and memory images and access logs, with who handled them. Never clean a compromised host before the security engineer says so.

### Start the breach clocks

The moment the team becomes aware of a possible breach, log the time. Clocks count from awareness, not the end of the investigation. Under GDPR the controller notifies the authority within 72 hours where feasible (Art. 33). Other regimes set other clocks and recipients. Each one, with its trigger, is in [references/breach-clocks.md](references/breach-clocks.md).

The runbook names the regimes that apply. When it does not, ask a person with legal authority at once. An agent gathers facts and drafts a notice. A person decides whether to notify, and sends it.

### Communicate

- Keep a cadence per audience (responders, support, leadership, customers, regulators), such as every 30 minutes for responders at high severity. Each update, even with no news, states impact, actions, and the next update time, never a guessed cause as fact. Templates: [references/updates.md](references/updates.md).

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Service restored check | the service is back for users | the SLI within its SLO for the window the runbook names, such as 30 minutes, and its smoke tests green |
| Incident regression test | the incident cannot recur unseen | a test reproducing it, in the backfill Spec, linked from `outcome.learn_ref` |

## Stop if

- No human commander is named, or you are about to act without the commander's agreement.
- You are diagnosing while a known rollback or mitigation waits, or evidence is about to be overwritten.
- An update is overdue, or a cause is announced before it is confirmed.
- Personal data may be involved and nobody recorded when the team became aware, or who decides on notification.

## Hand off

- Done: service restored, the timeline, the evidence list, and the emergency change with its backfill stub. Next: the commander declares the end; `/aidd-team:postmortem specs/INC-<n>.md` writes the blameless postmortem and finishes the backfill Spec by `review_due`. Needs: the commander's decisions, and a person for any customer or regulator notice. Stopped at: none, or the stop rule that fired.
