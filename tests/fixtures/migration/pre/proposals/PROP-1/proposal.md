---
aidd_version: "1.0.0"
type: proposal
id: PROP-1
title: Rebuild the shop
audience: client
addressee: Acme
goal: "Acme takes its orders on the new shop by 2027-03-01"
owner_team: core   # the team accountable for it
claims:
  - id: C-1
    text: The order export runs in under a minute.
    evidence: ["src/orders/export.py:42"]   # where it was seen
    scope: code
---

## Summary

A rebuild of the shop, in two phases.
