---
name: threat-model
description: "Practice skill: threat-model a change before code exists. Use when a Spec touches authentication, authorization, personal data, secrets, a trust boundary, a new integration or dependency, file uploads, multi-tenant data, or an AI feature, or when someone asks is this secure, what could an attacker do, STRIDE, abuse cases, or a security review before building: data-flow diagram, STRIDE per boundary, ASVS level, abuse cases that become tests, mitigations with owners."
metadata:
  checked: "2026-09-25"
---

# Threat model

**Use it when** a Spec touches auth, data, secrets, a trust boundary, a dependency, or an AI feature, and in Review when such a diff arrives.

**Do not use when** the change introduces no new data flow, trust boundary, actor, secret, or external input; a refactor inside one existing boundary has no new threat to model, and secure-coding is the practice for it.

## Standards

- STRIDE over a data-flow diagram.
- OWASP ASVS 5.0 (levels L1 to L3).
- OWASP Top 10 (2025) and the CWE Top 25.
- OWASP Top 10 for LLM Applications (2026) for AI features.
- NIST SSDF (SP 800-218).

## Specify, before Spec approval

- Draw the data flow: actors, processes, stores, and every trust boundary the change crosses or creates.
- For each boundary, list Spoofing, Tampering, Repudiation, Information disclosure, Denial of service, and Elevation of privilege threats, each with a mitigation and an owner.
- Choose the ASVS level (L1 most applications, L2 sensitive data, L3 critical systems) and name the requirements the change must meet.
- Turn each abuse case into a test the tester writes now; record the residual risk in the Spec.
- Write the model into the Spec's Design under "Threat model"; a large one becomes a documentation Task in `docs/security/`, written after Spec approval.

## Test commands

- The abuse-case tests this model produced, one per threat; DAST (OWASP ZAP) where a running service exists. `secure-coding` owns SAST, the dependency audit, and secret scanning — name them once, from there, because two commands with the same `name` in one Spec is a gate failure.

## Review

- Every mitigation the model names is in the diff; no new trust boundary or data flow appeared without a threat entry; security events are logged; no secret or personal data in code, tests, or logs.

## Hand off

- Done: the threat model and the abuse cases. Next: the tester (tests) and the human reviewer from the security pool. Needs: a decision on any residual risk above the profile's appetite. Stopped at: none, or the stop rule that fired.
