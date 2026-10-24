# Least privilege in code

Load this when a change adds a role, a permission, a token, or a service account. The access process around it (grants, reviews, joiners, movers, and leavers, break-glass) is `aidd-team:enterprise-controls`, `references/readiness.md`.

- Grant a role, never a person-by-person permission list. A role has an owner who approves each grant into it.
- Start every new role, token, and service account with nothing, and add only what a named Task needs. A wildcard permission (`*`, `admin`, `owner`) needs a reason in the Spec and a person's approval.
- Separate duties that must not meet in one person. Nobody approves their own grant, and the person who deploys is not the only one who can review the deploy.
- Agents get the narrowest access of all: a write area (the aidd guard) and a read-only CI token by default. They get no production data or console access unless a person grants it for one Task and removes it after.

Test: for each new permission, the role that holds it is allowed and every other role is denied (a row of the authorization matrix).
