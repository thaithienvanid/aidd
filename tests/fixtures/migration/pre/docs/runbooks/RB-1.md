---
aidd_version: "1.0.0"
type: runbook
id: RB-1
title: Restore the orders database
service: orders-db
owner_team: core
status: active
tested_on: "2026-11-01"
restore: true   # a restore from backups
rto: "4h"
rpo: "15m"
---

## Purpose

Restore the orders database from its last backup.
