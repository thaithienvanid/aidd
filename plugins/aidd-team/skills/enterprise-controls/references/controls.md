# The unified control set

Nineteen controls the product carries when compliance is on (`[project.compliance]` names a target, or the profile is regulated). Build each once and map it many times. Name the controls a change touches in the Spec's Context. In the compliance doc, write one row per obligation with its id (`EC-15`), so `aidd record export records --by-control` groups the evidence. A control's test is a `[[tests.commands]]` or `[[tests]]` entry: a test the gate never runs is guidance, not evidence. "Built" means aidd already produces the evidence. SOC 2 ids are the 2017 criteria (2022 points of focus); one marked *(unverified)* stays a pointer until a person confirms it. ISO ids are ISO/IEC 27001:2022 Annex A; GDPR items are articles. A mapping says the control contributes evidence; the auditor decides.

| Control | The product must | Test and evidence | Serves |
| --- | --- | --- | --- |
| EC-01 Change management (built) | change only through an approved, tested, recorded change | the Spec's tests red on base, green on head; the gate record | SOC 2 CC8.1; ISO 27001 8.32, 8.25; GDPR Art. 32 |
| EC-02 Input validation (built) | validate input at a trust boundary; never build a query, command, or path from it | a negative test per input; SAST | SOC 2 CC6.1, CC6.8; ISO 27001 8.28, 8.26; GDPR Art. 32 |
| EC-03 Deny-by-default authorization | deny unless a rule allows, server side, per object, from one authorization matrix | one test per matrix cell, another tenant and no session included | SOC 2 CC6.1, CC6.3; ISO 27001 5.15, 5.18, 8.3; GDPR Art. 25, 32 |
| EC-04 Secrets in a manager | load secrets at runtime, rotate them, never write one to the repository, a log, or a prompt | the secret scan (the `secrets` job of `aidd-security.yml` (GitHub) or the `aidd-secrets` job of `aidd-security.gitlab-ci.yml` (GitLab)); a redaction test | SOC 2 CC6.1; ISO 27001 5.17, 8.24; GDPR Art. 32 |
| EC-05 Secure architecture (built) | keep the architecture's trust boundaries as fitness functions | the fitness functions in `[[tests]]`; the ADRs | SOC 2 CC5.2; ISO 27001 8.27; GDPR Art. 25 |
| EC-06 Backup and a drilled restore (built) | back up every store of record and restore it on a schedule within its RTO and RPO | the restore drill's `tested_on` (`aidd doctor`) | SOC 2 A1.2, A1.3 *(unverified)*; ISO 27001 8.13, 8.14, 5.30; GDPR Art. 32 |
| EC-07 Threat model per risky Spec | model threats before a boundary, credential, personal-data, or authorization change | each mitigation's Acceptance test; the frozen threat model | SOC 2 CC3.2; ISO 27001 5.7, 8.25, 8.26; GDPR Art. 25, 35 |
| EC-08 Scanning and an SBOM | fail on a known-vulnerable dependency or a SAST finding; publish an SBOM | the dependency, static-analysis, and container scans; the SBOM | SOC 2 CC7.1, CC6.8; ISO 27001 8.8, 5.21, 8.7; GDPR Art. 32 |
| EC-09 CI least privilege | read-only tokens, actions pinned by SHA, no secret near untrusted code, signed provenance | a pinned workflow linter; the attestation | SOC 2 CC6.1, CC8.1; ISO 27001 8.4, 8.9, 8.31; GDPR none directly |
| EC-10 Logging with redaction | structured logs with a request id, redacted, and a security event per sign-in, failure, permission change, and denial | a test per event; a masking test | SOC 2 CC7.2; ISO 27001 8.15, 8.16, 8.17, 8.11; GDPR Art. 5, 32 |
| EC-11 Encryption and keys | TLS 1.2 or later with HSTS, every store encrypted at rest, keys in a KMS with rotation | a header test; an infrastructure check | SOC 2 CC6.1, CC6.7; ISO 27001 8.24, 8.20; GDPR Art. 32 |
| EC-12 Authentication hardening | SSO-ready (OIDC, SAML), MFA, lockout, idle expiry, session rotation, slow salted hashes | the session and lockout tests; an OIDC sign-in test | SOC 2 CC6.1, CC6.2; ISO 27001 8.5, 5.17, 5.16; GDPR Art. 32 |
| EC-13 Tenant isolation | keep each customer's data from every other, in the code and in the database | the cross-tenant tests (`aidd-team:multi-tenant-saas`) | SOC 2 CC6.1, C1.1; ISO 27001 8.3, 5.23; GDPR Art. 25, 32 |
| EC-14 Rate limiting | limit every endpoint; slow automated abuse of sign-in, sign-up, reset, and costly calls | request N+1 is refused, the next window served | SOC 2 CC6.6; ISO 27001 8.6, 8.20; GDPR Art. 32 |
| EC-15 Audit log | an append-only event per sign-in, permission, admin, configuration, and export action, readable by the tenant's admin | the audit event test; a sample export | SOC 2 CC7.2, CC7.3; ISO 27001 8.15, 5.28, 5.33; GDPR Art. 5(2), 30, 32 |
| EC-16 Access management | roles, joiner-mover-leaver, SCIM, scheduled reviews, sealed break-glass, one-purpose service accounts ([readiness.md](readiness.md)) | a deprovisioned user's sessions stop at once; a test per SCIM operation; review records | SOC 2 CC6.2, CC6.3; ISO 27001 5.15, 5.16, 5.18, 8.2; GDPR Art. 32 |
| EC-17 Incident response | a human commander, kept evidence, and the breach clocks `aidd-team:incident-response` lists | an incident drill; the postmortem and its actions | SOC 2 CC7.3, CC7.4, CC7.5, CC2.3 *(unverified)*; ISO 27001 5.24 to 5.28, 5.5, 6.8; GDPR Art. 33, 34 |
| EC-18 Vulnerability disclosure | a `security.txt` (RFC 9116) and a policy; fix by severity; tell customers | the regression test for the report; the advisory | SOC 2 CC7.1, CC7.4; ISO 27001 8.8, 5.5; GDPR Art. 32 |
| EC-19 Enterprise-deal items | the buyer's checklist ([readiness.md](readiness.md)): SSO and SCIM, MFA and lockout, session management, an audit log, an admin console, IP allowlisting, data residency, an SLA and status page, a trust center and security questionnaire, and a VPAT | each item's Acceptance tests; the deal checklist | SOC 2 CC6.1, CC6.6, A1.2; ISO 27001 5.15, 5.23, 5.31; GDPR Art. 28, 44 |

Per step:

1. Specify names the controls and their Acceptance.
2. Implement meets each in code, never in prose.
3. Review walks each named control against the diff.
4. Ship watches the control's signal in the observe window.
