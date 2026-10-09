# Enterprise readiness

What an enterprise buyer asks for before signing, how far along the product should be at each stage, and how access is granted and removed. The team builds the product side. The organizational side is people's work outside the team: policies, the ISMS, vendor reviews, training, the penetration test, and the auditor.

## The enterprise-deal checklist

Each item is a Spec with Acceptance a buyer could check; "done" is the evidence a security questionnaire asks for.

| Item | Done when | Control |
| --- | --- | --- |
| SSO | OIDC (and SAML where asked) against the customer's identity provider, with just-in-time provisioning and SSO required per tenant | EC-12 |
| SCIM | SCIM 2.0 (RFC 7643, 7644) creates, updates, and deactivates users and groups; a deactivated user's sessions and tokens stop at once | EC-16 |
| MFA | TOTP or WebAuthn for every account, and an admin setting that requires it | EC-12 |
| Lockout | repeated failed sign-ins lock or throttle, with a stated threshold and an unlock path that is not a support ticket | EC-12 |
| Session management | idle and absolute timeouts an admin sets, sign-out everywhere, the session id rotated at sign-in | EC-12 |
| Audit log | a tenant's admins read and export its audit log, with a stated retention | EC-15 |
| Admin console | a tenant admin manages users, roles, SSO, MFA, and settings under the same authorization matrix | EC-03, EC-19 |
| IP allowlisting | a tenant admin restricts sign-in and API access to named ranges, at the edge | EC-19 |
| Data residency | the region per tenant (`[project] hosting`), backups included, and the subprocessors per region | EC-19 |
| SLA and status page | an uptime commitment with its measurement and credits, backed by an SLO, and a public status page | EC-19 |
| Trust center and security questionnaire | the security overview, subprocessors, certifications, and ready answers (SIG Lite, CAIQ) drawn from the control set | EC-19 |
| VPAT | an Accessibility Conformance Report on the current VPAT template, backed by the accessibility tests | EC-19 |

## The readiness ladder

| Stage | The product has | Organizational work (outside the team) |
| --- | --- | --- |
| MVP | EC-01 to EC-04, EC-08, EC-09, and EC-11, with ASVS Level 1 | a named owner for security questions |
| First paying customer | plus EC-06, EC-10, EC-12, EC-14, EC-17, EC-18, and a privacy notice | a DPA template, the subprocessor list, an incident contact |
| First enterprise deal | compliance on: all 19 controls, the checklist above, and evidence by control | the questionnaire, a trust center, often a third-party penetration test |
| Certification | the same controls, with the evidence exported for the audit period | policies, the ISMS (ISO/IEC 27001 clauses 4 to 10), risk assessment, vendor reviews, training, and the auditor (SOC 2 Type I then Type II, or an ISO/IEC 27001 certification body) |

The team cannot certify the product: an independent auditor issues the report or the certificate. The team supplies the controls and their evidence, by control and by change.

## Access management (EC-16)

This section covers the product's access model and the team's tooling: the repository, CI, the cloud console, and production data. It follows NIST SP 800-53 AC-2, AC-5, and AC-6 and ISO/IEC 27001 5.15, 5.16, 5.18, and 8.2.

- **Joiner, mover, leaver.** Access starts from a role, through the identity provider or SCIM, never by hand in each tool. A move removes the old role's access in the step that grants the new one. A leaver's sessions, tokens, and keys end at once, in the product and the tools. Their service accounts move to an owner or are deleted.
- **Access review.** On a schedule, each role's owner confirms or removes each member, as a dated record. The schedule is quarterly for production and admin access, and at least yearly for the rest. An account unused for the period goes unless its owner says why. The review covers repository admins, CI secrets, cloud IAM, the database, observability tools, and each agent's credentials.
- **Break-glass.** One or two sealed emergency accounts per system, in a vault with two-person access. Every use pages the owners, is audit-logged (EC-15), and ends with the credential rotated.
- **Service accounts.** One purpose, named for it, with an owner and no human sign-in. Use workload identity or OIDC over a stored key. Where a stored key is used, it lives in the secret manager and rotates.
- **Tests.**
  - A deactivated user's next request fails.
  - One test per SCIM operation.
  - One allow and one deny per new permission.
  - A pinned workflow linter (zizmor or actionlint) in CI.
- **Stop if** one of these is true:
  - A grant would give an agent production data, a cloud console, or an approval right.
  - A role, token, or service account would have no owner.
  - A leaver's access cannot be removed at once.
