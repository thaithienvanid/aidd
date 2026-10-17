---
aidd_version: "1.0.0"
kind: runbook
id: "{{id}}"
title: "{{title}}"
service: "TODO: the service or system this procedure operates"
owner_team: "{{owner_team}}"
status: draft
# tested_on: "YYYY-MM-DD"   # the day a person last ran it end to end; `aidd doctor` warns when it grows old
# restore: true    # a restore from backups (disaster recovery): `aidd doctor` asks for rto and rpo and a recent drill
# rto: "4h"        # recovery time objective: the longest the service may be down
# rpo: "15m"       # recovery point objective: the most data, as time before the failure, a restore may lose
---

<!-- The SRE writes and keeps the runbook. Write it before it is needed, and test it on a schedule. Then the person
     paged at 3 a.m. follows steps that worked last month, not steps someone remembers. Every command is copy-paste ready. Every step says what you
     should see. An agent never runs a runbook's steps against a live system. It proposes them, and a person runs them
     (references/observe-learn.md). The sections come in the order a person on call reads them: what to do, how to
     know it worked, how to undo it, and whom to call. Rollout, Restore, and Handover follow, for the runbooks that
     need them.
     Write the prose at the `ste-80` level (the `aidd-team:plain-language` skill). -->

Spec: {{spec}}. <!-- the change this runbook rolls out. `aidd new runbook <ID> --spec <SPEC>` links it from that Spec
     as a living doc (frozen: false), so it stays current after the merge. Write `none` for a standing procedure. -->

## Purpose

<!-- What this procedure restores or changes, in one or two sentences, and what it must never do. -->

## When to use

<!-- The alert, symptom, or request that sends someone here, and the look-alikes that should not. -->

## Prerequisites

<!-- Access, tools, credentials (named, never pasted), and the state the system must be in first. -->

## Steps

<!-- Numbered. One action per step, with the exact command and the output that means it worked. -->

1. TODO

## Verification

<!-- How you know the service is healthy again: the dashboard, query, or check, and the value to expect. -->

## Rollback

<!-- How to undo each step that changed something, and when to stop and roll back instead of going on. -->

## Escalation

<!-- Who to call when a step fails or the verification does not hold, in order, and how to reach them. -->

## On-call

<!-- Who answers when this service pages, for a standing service; delete it for a one-off rollout. Link the team's
     paging tool and rota instead of copying them. An agent never pages or acknowledges a page. -->

- Rota: TODO: the schedule's link, the rotation length, and the hours it covers (business hours or 24/7)
- Escalation: TODO: primary, then secondary after N minutes without an acknowledgement, then the service owner
- Handover: TODO: when shifts change, and what the outgoing person hands over (open incidents, silenced alerts, risky changes in flight)
- Paging policy: TODO: the link to what pages a person (an SLO burn or a symptom) and what only opens a ticket

## Rollout

<!-- For a change that ships with this runbook (a major Spec asks for one). Cover:
     - the stages and their order (a canary, a percentage, a region)
     - the feature flag, and who flips it
     - what to watch at each stage, and for how long (the Spec's `observe` signals)
     - the rollback trigger, and the point of no return.
     Delete it for a standing procedure. -->

<!-- One row per ring, in order. Write each threshold before the ring starts, never after you see its numbers. Tag
     the metrics with the flag state, so on compares with off. Keep the shadow ring for pricing, billing, permissions,
     and other risky logic: the new path runs with no side effects, and its results are compared with the old path's.
     Delete a ring the change does not need. -->

| Ring | Audience | Go threshold | No-go threshold | Watch for |
| --- | --- | --- | --- | --- |
| 0. Shadow | nobody: the old path serves | TODO: results match on N requests | TODO: any difference not explained | TODO |
| 1. Team | TODO | TODO | TODO | TODO |
| 2. Internal | TODO | TODO | TODO | TODO |
| 3. Canary | TODO: 1 to 10% | TODO | TODO | TODO |
| 4. Everyone | all users | TODO: stable for N days | TODO | TODO |

### Launch readiness

<!-- The go/no-go owner checks these before the first stage. Each line names the person who owns it. A line that does not apply says why. -->

- [ ] Comms (owner TODO): internal (the teams who will be asked about it), customers (the announcement), and the status page if it can degrade service
- [ ] Support (owner TODO): the support team briefed, and the knowledge base (KB) article or macro ready
- [ ] Docs (owner TODO): user docs and release notes written
- [ ] Legal and compliance (owner TODO): the terms of service and privacy notice updated, and the DPIA or compliance doc linked when the change needs one
- [ ] Operations (owner TODO): dashboards and alerts live, on-call named, and backups with a tested restore for each stateful part
- [ ] Feature flag: flag owner TODO, default TODO, cleanup date YYYY-MM-DD for removing the flag
- [ ] Go/no-go owner TODO: the person who decides, and when
- [ ] Point of no return (owner TODO, who approves going past it): TODO, the step after which rollback means restore

## Restore

<!-- For a stateful service (a database, a bucket, a queue that holds data): how to restore it from its backups. Set
     `restore: true`, `rto`, and `rpo` in the front matter. Cover:
     - where the backups are, and how long they are kept
     - the commands that restore into a scratch environment first
     - how to check the data is complete up to the RPO
     - the time the last drill took against the RTO.
     A person drills it on a schedule and records `tested_on`. `aidd doctor` warns when the restore drill is older than
     `runbook_max_age_days`. Delete it for a stateless procedure. -->

## Handover

<!-- For a client engagement, before the client's team runs this service (`/aidd-team:handover`); delete it otherwise.
     The acceptance record's Handover section holds the client's sign-off. Name each credential with where it now
     lives, never a secret itself. -->

- [ ] Docs index: where the user, admin, and API docs, this runbook, and the architecture overview live
- [ ] Credentials transfer: each account, key, and certificate moved to the client's owner and vault, then rotated
- [ ] Training: the client's operators ran this runbook once with us, on a date recorded here
- [ ] Open issues: known defects and gaps handed over, each with its Spec or issue
- [ ] Warranty start: the date the contract's warranty begins, and the contract's support levels that apply after it
