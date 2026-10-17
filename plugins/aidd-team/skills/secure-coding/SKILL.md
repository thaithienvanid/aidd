---
name: secure-coding
description: "Practice skill: write and change code securely. Use in an aidd repository when a Task handles input, auth, secrets, config, files, SQL, shell, or crypto, or on any Implement Task."
metadata:
  checked: "2026-09-30"
---

# Secure coding

**Use it when** a Task names it in `skills`, or an Implement Task names no practice skill. The threat model says what to defend; this skill says how. By default only the **Default** rules apply (minimum change holds: add no module, lint, or scanner the Spec did not ask for). ASVS Level 1 is the default.

**Do not use when** the change touches no input, secret, credential, permission, cryptography, serialization, or untrusted content, and adds no dependency; a docs-only change has no attack surface.

## Standards

<!-- aidd:gen practice:secure-coding -->
| Standard | Edition |
| --- | --- |
| OWASP Top 10 and the CWE Top 25 | OWASP Top 10:2025; CWE Top 25 (2025 list) |
| OWASP ASVS 5.0: Level 1 by default; Level 2 for authentication, session, and admin surfaces under compliance | 5.0.0 |
| OWASP Cheat Sheet Series (XSS, CSRF, clickjacking) | — |
| NIST SSDF (SP 800-218) | SP 800-218 v1.1 |
| OWASP Developer Guide secure coding checklists, and the OWASP Abuse Case method | — |
| Secrets outside the repository and scanned before commit; scoped private registries against dependency confusion | — |
| RFC 9700 OAuth 2.0 Security Best Current Practice | RFC 9700 (BCP 240) |
| NIST SP 800-63-4 Digital Identity Guidelines | SP 800-63-4 |

Each standard's checked date and source are in the aidd-team roles reference (`references/roles.md` in `aidd-team:aidd-team`), section `aidd-team:secure-coding`.
<!-- aidd:end -->

## Implement

**Default**, for the code the change touches:

- Validate every input at a trust boundary against an allow-list or a schema; reject, never repair.
- Queries are parameterized; never build a shell command from input.
- Authorization is checked on every path and object, server side, deny by default.
- Secrets come from the environment or a secret manager, never code, repository config, logs, or prompts.
- A new dependency is verified on the official registry (no look-alike name), maintained, free of advisories, lockfile-pinned, and allowed by the Spec.

**When the Task names this skill, or the route is major**, add:

- Output is encoded for its context; untrusted data never meets a general-purpose deserializer.
- One configuration boundary: one module reads the environment and the secret manager and validates every setting at start-up; a lint rule bans environment access elsewhere; when in doubt, a setting is a secret: [references/configuration.md](references/configuration.md).
- Cryptography from the platform library with current defaults; nothing home-grown or deprecated.
- Safe defaults: timeouts, size and rate limits, generic errors to users; paths normalized and confined to their root.
- Log facts, never sensitive values, through the one redaction step, and security events with their actor (`aidd-team:observability`).
- Least privilege for a new role, permission, token, or service account: [references/least-privilege.md](references/least-privilege.md).
- **Authentication and sessions** (OAuth or OIDC, passkeys, MFA, recovery): [references/authentication.md](references/authentication.md).
- The `security_headers` product default: `aidd-team:product-defaults`.

## Review

- Trace each untrusted input to its sinks; check new dependencies, error handling for leaks, and the threat model's mitigations.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Input and authorization tests | a rejected input, an allowed and a denied caller, a parameterized query, and no secret in a log line | unit tests of what the change touched. When the Task names this skill, or the route is major, add the rows below and the scans |
| Parser fuzzing | every parser survives malformed input | libFuzzer, AFL++, or Jazzer on each parser |
| Configuration boundary lint | no module outside the boundary reads the environment | a rule in the repository's linter |
| Session rotation test | sign-in rotates the session id; sign-out and timeouts end it | integration |
| Lockout and throttling tests | failed sign-ins throttle at the threshold | integration |
| MFA and recovery tests | a missing factor or a reused refresh token is refused | integration |

- From `aidd-team:enterprise-controls`: Dependency scan, Static analysis, Secret scan (OSV-Scanner, Semgrep, gitleaks, pinned there), on the head when this skill applies.
- From `aidd-team:observability`: Redaction test, Security event tests.

## Stop if

- A secret would land in code, repository config, a log, or a prompt.
- A new dependency's name or publisher does not match the official registry's.
- An exception to a rule has no named risk and no person's decision.

## Hand off

- Done: the code, its security tests green. Next: the reviewer, and the security engineer on major. Needs: an exception to a rule, with the risk named. Stopped at: none, or the stop rule that fired.
