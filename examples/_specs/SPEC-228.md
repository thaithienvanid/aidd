+++
aidd_version = "1.0.0"
kind = "spec"
id = "SPEC-228"
title = "Let customers set a preferred name"
owner_team = "checkout"
type = "feat"
route = "normal"
confidence = "high"
open_questions = []
trace_id = "spec-228"
assisted_by = ["claude-code/claude-opus-5-5"]
rollback = "Revert the PR; the order confirmation greets the customer by their account name again."
residual_risk = "A preferred name saved before the rollback stays stored until the next erasure run."

[risk]
summary = "Adds an optional preferred name to the customer profile and shows it on the order confirmation."
dimensions = []
reversible = true

[[tasks]]
id = "TASK-228"
title = "Store and show the preferred name"
scope = ["src/customers/profile.py"]
assignee = "agent:claude-code"

[tests]
files = ["tests/customers/test_preferred_name.py"]

[[tests.commands]]
name = "preferred-name"
command = ["python3", "-m", "pytest", "tests/customers/test_preferred_name.py"]
new_behavior = true

[observe]
window = "24h"
signals = "profile update errors, order confirmation errors"
rollback_trigger = "profile update errors above 1% for 10 minutes"
+++

## Context

Customers want the order confirmation to use the name they go by. The profile lives in `src/customers/profile.py`.

## Acceptance

```gherkin
Given a customer who set a preferred name
When the customer places an order
Then the confirmation greets them by the preferred name
```
