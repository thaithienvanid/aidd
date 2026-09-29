+++
aidd_version = "1.0.0"
kind = "runbook"
id = "{{id}}"
title = "{{title}}"
service = "TODO: the service or system this procedure operates"
owner_team = "{{owner_team}}"
status = "draft"
# last_tested = "YYYY-MM-DD"   # the day a person last ran it end to end; `aidd doctor` warns when it grows old
+++

<!-- A runbook is written before it is needed and tested on a schedule, so the person paged at 3 a.m.
     follows steps that worked last month, not steps someone remembers. Every command is copy-paste
     ready; every step says what you should see. An agent may run a runbook only when a person has
     approved it for that (references/observe-learn.md); otherwise it proposes the steps. -->

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
