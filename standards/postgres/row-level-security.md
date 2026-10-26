---
id: postgres/row-level-security
type: opinionated
fills: [multi-tenant-saas:tenant-isolation]
default: true
implements: multi-tenant-saas:Row-level security enforced
roles: [architect, developer, security-engineer, reviewer]
when_changed: ["migrations/**", "modules/*/migrations/**", "**/*.sql"]
why: "Shared tables with a tenant id and a row security policy cost one schema for every tenant, and PostgreSQL refuses another tenant's rows even where a query forgets its filter."
reviewed: "2026-10-22"
maturity: established
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [a schema for each tenant, a database for each tenant]
status: active
source: https://www.postgresql.org/docs/current/ddl-rowsecurity.html
evidence: Superusers and roles with the BYPASSRLS attribute always bypass the row security system when accessing a table.
---

# Row-level security keeps tenants apart in shared PostgreSQL tables

It answers the tenant-isolation choice of `aidd-team:multi-tenant-saas` on PostgreSQL.

## What PostgreSQL supports

As read on the `checked` day: a superuser, a role with `BYPASSRLS`, and a table's owner skip the policies, unless the table sets `FORCE ROW LEVEL SECURITY`. A table with row security on and no policy shows no rows.

## What the team does

- Give every tenant table a `tenant_id` column, not null, that leads its primary key and each of its indexes.
- In the migration that creates the table, run `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`. Add one policy, `USING (tenant_id = current_setting('app.tenant_id')::uuid)`, with the same `WITH CHECK`.
- Connect the application under a role that owns no table, is no superuser, and has no `BYPASSRLS`. Run the migrations under the owner role.
- Set the tenant at the start of each transaction with `SET LOCAL app.tenant_id`, from the authenticated session. A pooler in transaction mode then never carries one request's tenant into the next.
- Without the setting, the cast fails or the policy matches nothing, so a query with no tenant sees no other tenant's rows.
- Run a job across tenants, such as billing, under its own role and its own policy, never under the application's role.

## What the gate runs

Nothing of its own. The pack's Row-level security enforced test connects as the application role and proves the policies hold.
