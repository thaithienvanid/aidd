# Policy as code

The Policy interface is aidd's extension point. Any command works; it runs from a clean worktree of the base branch, with no tokens, and answers with one word (`allow`, `deny`, `freeze`) or one JSON object:

```json
{"verdict": "allow", "detail": "org policy v1",
 "findings": [{"rule": "payments-ticket", "level": "fail",
               "message": "src/payments/charge.py changes payments, but the description links no PAY- ticket",
               "fix": "add the PAY- ticket to the PR description"}]}
```

Findings join the gate's decision as rules named `policy:<rule>`, at level `fail`, `pending`, or `warn`. The command reads the change from the JSON file at `AIDD_INPUT_FILE`: `change_id`, `base_sha`, `head_sha`, `route`, `type`, `paths`, and `body`.

This folder shows the pattern with OPA and Rego:

- [`aidd.rego`](aidd.rego) freezes on listed dates, requires a ticket link for payments changes, and warns on edits to generated clients.
- [`aidd-policy-opa`](aidd-policy-opa) evaluates it and prints the JSON answer.

To use it, copy both into `scripts/`, install `opa` from a pinned release in the gate workflow, and bind `policy: ["./scripts/aidd-policy-opa"]`. The bound script's whole directory becomes protected (here `scripts/**`), so changing a rule, the wrapper, or a helper next to it is a major change with a security review. The same protocol works for CEL, a Python script, or a call to an internal policy service. Another common Policy freezes feature routes while a service's SLO error budget is spent, and lets reliability work through by path. The emergency route passes a freeze either way.
