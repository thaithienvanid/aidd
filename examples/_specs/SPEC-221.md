+++
aidd_version = "1.0.0"
kind = "spec"
id = "SPEC-221"
title = "Only organization owners may create organizations"
owner_team = "checkout"
type = "security"
route = "major"
confidence = "high"
open_questions = []
trace_id = "spec-221"
assisted_by = ["claude-code/claude-opus-5-5"]
rollback = "Revert the PR, redeploy, then confirm that a member can create an organization in staging."
residual_risk = "Members who relied on self-service creation must ask an owner."

[risk]
summary = "Members lose the ability to create organizations; owners keep it."
dimensions = ["security"]
reversible = true

[[tasks]]
id = "TASK-221"
title = "Gate organization creation on the owner role"
scope = ["src/auth/organization.ts"]
assignee = "agent:claude-code"

[tests]
files = ["tests/auth/org-create.test.ts"]

[[tests.commands]]
name = "org-create"
command = ["npx", "vitest", "run", "tests/auth/org-create.test.ts"]
new_behavior = true

[observe]
window = "24h"
signals = "403 rate on POST /organization/create, support tickets tagged org-create"
rollback_trigger = "An owner receives 403 on organization creation"
+++

## Context

The Better Auth organization plugin reads allowUserToCreateOrganization. Today every member may create an organization.

## Acceptance

| Caller role | POST /organization/create |
| --- | --- |
| owner | 200 |
| member | 403 |
| anonymous | 401 (unchanged) |
