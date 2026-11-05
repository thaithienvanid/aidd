---
aidd_version: "1.0.0"
type: runbook
id: "{{id}}"
title: "{{title}}"
service: "TODO: the service or system this procedure operates"
delivery_team: "{{delivery_team}}"
status: draft
# tested_on: "YYYY-MM-DD"   # the day a person last ran it end to end; `aidd doctor` warns when it grows old
# restores_data: true    # a restore from backups (disaster recovery): `aidd doctor` asks for rto and rpo and a recent drill
# rto: "4h"        # recovery time objective: the longest the service may be down
# rpo: "15m"       # recovery point objective: the most data, as time before the failure, a restore may lose
---

<!-- The SRE writes and keeps the runbook. Write it before it is needed, and test it on a schedule. Then the person
     paged at 3 a.m. follows steps that worked last month, not steps someone remembers. Every command is copy-paste ready. Every step says what you
     should see. An agent never runs a runbook's steps against a live system. It proposes them, and a person runs them
     (references/observe-learn.md). The sections come in the order a person on call reads them: what to do, how to
     know it worked, how to undo it, and whom to call. Restore follows, for a stateful service. This is the standing
     procedure only. One change's rollout plan is the Spec's `## Rollout` (references/spec-release.md), the rota is the
     service card's, and the client handover is the acceptance record's.
     Write the prose at the `instruction` level (the `aidd-team:plain-language` skill). -->

Spec: {{spec}}. <!-- the change that added this procedure, such as a new failure mode. `aidd new runbook <ID> --spec <SPEC>`
     links it from that Spec as a living doc (frozen: false), so it stays current after the merge. Write `none` for a
     standing procedure. -->

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

<!-- Who to call when a step fails or the verification does not hold, in order, and how to reach them. The rota, the
     escalation order, and the paging policy are the service's: link its card (`docs/services/<service>.md`). An agent
     never pages or acknowledges a page. -->

## Restore

<!-- For a stateful service (a database, a bucket, a queue that holds data): how to restore it from its backups. Set
     `restores_data: true`, `rto`, and `rpo` in the front matter. Cover:
     - where the backups are, and how long they are kept
     - the commands that restore into a scratch environment first
     - how to check the data is complete up to the RPO
     - the time the last drill took against the RTO.
     A person drills it on a schedule and records `tested_on`. `aidd doctor` warns when the restore drill is older than
     `docs.max_runbook_age_days`. Delete it for a stateless procedure. -->
