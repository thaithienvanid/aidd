+++
aidd_version = "1.0.0"
kind = "spec"
id = "SPEC-222"
title = "Round invoice totals half-even"
owner_team = "checkout"
type = "fix"
route = "normal"
confidence = "high"
open_questions = []
trace_id = "spec-222"
assisted_by = ["claude-code/claude-opus-5-5"]
rollback = "Revert the PR."
residual_risk = "none"

[risk]
summary = "Invoice totals ending in exactly half a cent round to even instead of up."
dimensions = []
reversible = true

[[tasks]]
id = "TASK-222"
title = "Use half-even rounding in totals"
scope = ["src/checkout/totals.py"]

[tests]
files = ["tests/checkout/test_totals.py"]

[[tests.commands]]
name = "totals"
command = ["pytest", "-q", "tests/checkout/test_totals.py"]
new_behavior = true
+++

## Context

Finance reported off-by-one-cent totals on half-cent amounts.

## Acceptance

| Subtotal | Total |
| --- | --- |
| 10.005 | 10.00 |
| 10.015 | 10.02 |
