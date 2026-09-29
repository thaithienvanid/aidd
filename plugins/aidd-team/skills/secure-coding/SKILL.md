---
name: secure-coding
description: "Practice skill: write and change code securely. Use by default on an Implement Task whose `skills` names none, and when a Task names it, or when code handles user input, authentication, sessions, permissions, secrets, API keys, environment variables, configuration, file paths, uploads, serialization, SQL, shell commands, or cryptography, or when someone mentions a vulnerability, injection, XSS, SSRF, a leaked secret, or a security scan finding: validation at trust boundaries, parameterized queries, output encoding, authorization on every path, one configuration boundary, secrets and logging rules, verified and pinned dependencies, and the test commands that prove them."
metadata:
  checked: "2026-09-28"
---

# Secure coding

**Use it when** a Task names it in `skills`, or by default when an Implement Task names no practice skill; a Task names at most two, so it never rides along uninvited. The threat model says what to defend, this skill says how.

**Do not use when** the change touches no input, secret, credential, permission, cryptography, serialization, or untrusted content, and adds no dependency; a docs-only change has no attack surface to reduce.

## Standards

- OWASP Top 10 (2025) and the CWE Top 25.
- OWASP ASVS 5.0 at the Spec's level.
- The OWASP Cheat Sheet Series.
- NIST SSDF PW practices.
- The OWASP Logging Cheat Sheet and the OWASP Application Logging Vocabulary.
- Package names verified against look-alikes (slopsquatting).

## Implement

- Validate every input at a trust boundary against an allow-list or a schema; reject, never repair.
- Queries are parameterized; output is encoded for its context (HTML, attribute, or URL; never build a shell command from input); untrusted data is never deserialized with a general-purpose deserializer.
- Authorization is checked on every path and every object, server side, with deny by default.
- Secrets come from the environment or a secret manager, never from code, config in the repository, logs, or prompts.
- One configuration boundary: a single module reads the environment and the secret manager, validates every setting at start-up, and hands typed values to the rest of the code. No other module reads the environment, and a lint rule enforces it. Classify each setting as secret, environment configuration, build configuration, or constant; when in doubt, it is a secret. Table and lint rules: [references/configuration.md](references/configuration.md).
- Cryptography uses the platform library with current defaults; no home-grown algorithms, no deprecated modes.
- Safe defaults everywhere: timeouts, size limits, rate limits, and generic error messages to users with details in logs.
- Files and paths are normalized and confined to their root; temporary files are private.
- A new dependency is verified on the official registry, checked for maintenance and advisories, pinned by lockfile, and allowed by the Spec.
- Log the fact, not the sensitive value, through one redaction step that masks secret and personal fields by a case-insensitive key deny-list, in nested structures too (`aidd-team:observability` has the mechanism and its test).
- Log the security events with the actor: authentication success and failure, authorization denial with the resource, privileged operations, rate-limit hits, and repeated authentication failures.

## Test commands

- SAST (Semgrep, CodeQL); dependency audit (OSV-Scanner, `pip-audit`, `npm audit`); secret scanning (gitleaks); authorization and input-validation unit tests; fuzzing (libFuzzer, AFL++, Jazzer) for every parser.
- The lint rule that bans environment access outside the configuration boundary; the redaction unit test; a test per security event that asserts it is logged, and that the logged line holds no secret.

## Review

- Trace each untrusted input to its sinks; check every new dependency; check error handling for leaks; check that the threat model's mitigations are present.

## Hand off

- Done: the code and its security tests green. Next: the reviewer, and the security engineer on major. Needs: an exception to a rule, with the risk named. Stopped at: none, or the stop rule that fired.
