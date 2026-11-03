# Authorization matrix: {{title}}

Spec: [{{spec}}][spec]. Written {{today}}. Frozen at Spec approval with the Spec.

<!-- The security engineer writes this in Specify, before Spec approval (`aidd new authz <topic> --spec <ID>
     --no-link`). The architect links it as kind `authz`. Write it when the Spec's risk names security and a Task
     touches authentication or authorization code. The required-docs matrix warns without one. The threat model's
     Elevation of privilege rows point here.
     The verifier writes one test per row, and each test asserts the expected allow or deny. The verifier puts the test id
     in the last column, and the Acceptance id it proves in a test command's `covers`. A cell with no test is an
     untested permission.
     Write the prose at the `ste-80` level (the `aidd-team:plain-language` skill). -->

Every endpoint requires authentication unless it is listed under Public endpoints. The system denies anything this matrix does not allow.

## Subjects

<!-- Each role or principal that can call the system, including the anonymous caller, a service account, and an
     administrator of another tenant. -->

| Subject (role or principal) | How it is identified | Tenant |
| --- | --- | --- |
| anonymous | no credential | none |
| TODO: member | TODO: session, token scope | own tenant |
| TODO: admin | TODO | own tenant |

## Matrix

<!-- One row per subject, action, and resource or endpoint: the whole grid, the denies as well as the allows. A deny
     row is the test that catches a missing check. -->

| Subject (role or principal) | Action | Resource or endpoint | Condition (row-level policy) | Expected | Test id |
| --- | --- | --- | --- | --- | --- |
| anonymous | TODO: read | TODO: GET /orders | none | deny | TODO |
| TODO: member | TODO: read | TODO: GET /orders/{id} | the order's owner is the caller | allow | TODO |
| TODO: member | TODO: read | TODO: GET /orders/{id} | the order belongs to another user | deny | TODO |
| TODO: admin | TODO: delete | TODO: DELETE /orders/{id} | same tenant | allow | TODO |

## Row-level policies

<!-- The conditions the matrix names, each stated once, with where it is enforced (the query, a policy engine, a
     database row-level security policy). -->

| Policy | Rule | Enforced in | Test id |
| --- | --- | --- | --- |
| TODO: owner only | TODO: `order.user_id = caller.id` | TODO | TODO |

## Tenant isolation

<!-- For a multi-tenant system: every read, write, list, search, export, and cache key is scoped to the caller's
     tenant. One row per action, each a deny for a caller from another tenant. Delete this section for a single-tenant
     system and say so. -->

| Subject (role or principal) | Action | Resource or endpoint | Condition (row-level policy) | Expected | Test id |
| --- | --- | --- | --- | --- | --- |
| TODO: admin of another tenant | read | TODO: GET /orders/{id} | the order belongs to this tenant | deny | TODO |
| TODO: admin of another tenant | list | TODO: GET /orders | results from this tenant | deny | TODO |

## Public endpoints

<!-- The only endpoints that need no authentication, each with why. Everything else requires it. -->

| Endpoint | Why it is public | Test id |
| --- | --- | --- |
| TODO: GET /health | TODO | TODO |

[spec]: {{spec_link}}
