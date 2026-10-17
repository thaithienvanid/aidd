---
name: threat-model
description: "Practice skill: threat-model a change before code exists. Use in an aidd repository when a Spec touches auth, personal data, secrets, a trust boundary, or an AI feature."
metadata:
  checked: "2026-09-30"
---

# Threat model

**Use it when** a Spec touches auth, data, secrets, a trust boundary, a dependency, or an AI feature, and in Review of such a diff.

**Do not use when** the change adds no data flow, trust boundary, actor, secret, or external input; a refactor inside one existing boundary has no new threat, and secure-coding is its practice.

## Standards

<!-- aidd:gen practice:threat-model -->
| Standard | Edition |
| --- | --- |
| STRIDE threat modeling with data-flow diagrams | — |
| OWASP ASVS | 5.0.0 |
| OWASP Top 10 and the CWE Top 25 | OWASP Top 10:2025; CWE Top 25 (2025 list) |
| OWASP Top 10 for LLM Applications | 2026 edition |
| NIST SSDF (SP 800-218) | SP 800-218 v1.1 |

Each standard's checked date and source are in the aidd-team roles reference (`references/roles.md` in `aidd-team:aidd-team`), section `aidd-team:threat-model`.
<!-- aidd:end -->

## Specify

- Draw the data flow: actors, processes, stores, and each trust boundary the change crosses or creates.
- Per boundary, list Spoofing, Tampering, Repudiation, Information disclosure, Denial of service, and Elevation of privilege threats, each with a mitigation and an owner.
- Choose the ASVS level (L1 most applications, L2 sensitive data, L3 critical systems) and name the requirements the change must meet.
- Each abuse case becomes a test the tester writes now; record the residual risk in the Spec.
- Keep one living model per component, never one per Spec: `aidd new threat-model <component> --spec <ID>` writes `docs/security/threat-models/<component>.md` once, and links it again for each later Spec.
- The Spec holds only its delta: the threat ids it adds, changes, or retires (`T-<COMPONENT>-NN`, never reused), in the tech spec's "Security and privacy" or the Spec's Design. Spec approval freezes the delta; bring the model in line in the same change.
- Review the whole model once per release, not only the deltas.
- A model the next change will extend may also be a file beside the code: a Threat Dragon model or a pytm script.

## Review

- Every mitigation the delta names is in the diff, and the component's model matches the delta.
- No trust boundary or data flow appeared without a threat entry; security events are logged; no secret or personal data in code, tests, or logs.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Abuse-case tests | each threat's mitigation holds | one test per abuse case, red without the mitigation |
| Threat model as code | the diagram and threat list regenerate from the model without drift | pytm (1.4.0) `tm.py --dfd` and `--report`, then a diff check; or a Threat Dragon (v2.6.2) JSON model |

- From `aidd-team:apis-and-services`: OWASP ZAP API scan, where a running service exists.
- From `aidd-team:enterprise-controls`: Static analysis, Dependency scan, Secret scan. Name each once, from its owner: two commands with one `name` in a Spec fail the gate.

## Stop if

- A trust boundary the change crosses has no threat entry, or a threat has no mitigation and no owner.
- An abuse case stays a note, not a test.
- The residual risk exceeds the profile's appetite and no person has decided on it.

## Hand off

- Done: the threat model and the abuse cases. Next: the tester (tests) and the human reviewer from the security pool. Needs: a decision on any residual risk above the profile's appetite. Stopped at: none, or the stop rule that fired.
