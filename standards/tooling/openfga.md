---
id: tooling/openfga
type: opinionated
fills: [product-defaults:access-control]
default: true
implements: secure-coding:Input and authorization tests
roles: [architect, security-engineer, developer, reviewer]
when_changed: ["**/*.fga", "**/*.fga.yaml", "**/openfga/**", "**/authz/**"]
why: "OpenFGA answers fine-grained permission checks from one model, after Google Zanzibar, that every service asks. Access that follows relationships, such as sharing or nested teams, is then decided in one place. It is a CNCF incubating project under Apache-2.0."
maturity: established
tool:
  name: openfga
  registry: github
  package: openfga/openfga
version_policy: current_stable
checked_version: "v1.22.1"
checked: "2026-11-04"
checked_by: agent:claude-code/claude-opus-5-5
citation:
  url: https://raw.githubusercontent.com/openfga/openfga/main/README.md
  quote: "is a high-performance, flexible authorization/permission engine inspired by"
alternatives: [roles in the application's code, Cedar, Open Policy Agent, SpiceDB, Casbin]
status: active
---

# OpenFGA decides the permissions that follow relationships

It answers the access-control choice of `aidd-team:product-defaults` once roles in code stop fitting: a document shared with one person, a folder whose files inherit its access, or teams inside teams. OpenFGA is under the Apache-2.0 license. The CNCF accepted it on September 14, 2022, and moved it to incubating on October 28, 2025. Auth0 FGA has run it in production since December 2021.

## What the team does

- Keep the authorization model in the repository, in OpenFGA's modeling language, beside a test file of checks that must allow and checks that must deny. Run those tests with the OpenFGA CLI in CI, one per cell of the authorization matrix.
- Run the server as a service of its own on PostgreSQL or MySQL. Keep the in-memory store for tests.
- Call it through the official SDK for the language, with one question per check: may this user take this action on this object?
- Write each relationship tuple through an outbox, from the transaction that changes the data, so the model and the data never drift apart.
- Keep a role that never depends on a relationship in code, and ask OpenFGA only where a check needs the graph.
