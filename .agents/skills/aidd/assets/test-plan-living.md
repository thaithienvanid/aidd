---
reviewed_on: "{{today}}"
---

# Test plan: {{title}}

The living test plan of one component. First written for [{{spec}}][spec], {{today}}. Each later change that adds a risk or a test case outside a Spec's Acceptance updates this file in the same change.

<!-- The verifier writes and keeps this file: one per component, at docs/testing/test-plans/<component>.md.
     `aidd new test-plan <component> --living --spec <ID>` writes it once; a later Spec runs the same command to link it
     again. It is living, so no Spec approval freezes it, and Merge approval reviews it. A Spec's own plan
     (`aidd new test-plan <topic> --spec <ID>`) is frozen and states only its deviations and its new risks. At the change
     that lands the Spec, the verifier folds those risks into the register below.
     This is what an auditor reads. It follows ISO/IEC/IEEE 29119-3:2021, tailored (clause 4.1.3). Set `reviewed_on`
     in the front matter each time you review it: `aidd doctor` warns when the date is stale.
     Never restate what another file owns:
     - the Acceptance text (cite ids) and the thresholds (the SLO)
     - the tests themselves: their code, commands, and `covers` (each Spec's `tests`)
     - the results (the `aidd test` evidence) and the threats (the threat model, by id).
     Cite an Acceptance id of a Spec as `SPEC-n/A1`.
     Write the prose at the `instruction` level (the `aidd-team:plain-language` skill). -->

## Conformance

<!-- Tailored conformance to 29119-3:2021. Keep this table: it says where each information item lives in aidd. -->

Component: TODO. Owner: TODO. Conformance: tailored, ISO/IEC/IEEE 29119-3:2021.

| 29119-3 item | Where it lives |
| --- | --- |
| 7.2.2 context, 7.2.3 assumptions and constraints | Scope and test basis, below; each Spec's plan, Scope |
| 7.2.4 stakeholders, 7.2.5 communication | each Spec's plan, Audit additions and Reporting |
| 7.2.6 risk register | Risk register and coverage, below |
| 7.2.7 test strategy | Test strategy and Environments and matrix, below; each Spec's plan, Test approach |
| 7.2.8 activities and estimates, 7.2.9 staffing, 7.2.10 schedule | each Spec's Tasks and plan, Audit additions |
| 7.3 status report | the verification report and the `aidd test` evidence of the head under test |
| 7.4 completion report | each head's verification report and `aidd test` evidence |
| 8.2 test model, 8.3 test cases | Test catalog, below; each Spec's acceptance tests |
| 8.4 test procedures | omitted, because each test command in a Spec's `tests` is its own procedure |
| 8.5 data, 8.6 environment requirements | Environments and matrix, below |
| 8.7 test data readiness, 8.8 test environment readiness | omitted, because `aidd test` runs on a clean tree of the head and fails when the environment is not ready |
| 8.9 actual results and test result, 8.10 execution log | `aidd test` evidence and its logs, bound to a commit |
| 8.11 incident reports | omitted, because a defect goes to the project's tracker or the verification report, and a regression test lands in the Test catalog |

## Scope and test basis

<!-- The component's paths, the standards and Acceptance it must meet, and what is out of scope, each with why. -->

TODO: the component's paths, the standards it must meet, and what is out of scope.

## Test strategy

<!-- Say which levels you use and what each proves (a few unit tests at the base, fewer integration and contract tests,
     very few end to end). Say which of the four quadrants are covered (business or technology facing, supporting the
     team or critiquing the product). State the mock policy (mock only what you do not own or cannot run in CI). Name
     the regression suite, and say whether you use mutation testing and how a flaky test is handled (a finding, never a
     re-run). Link the config's `tests` commands, and do not copy them. -->

| Level | What it proves | Real | Mocked |
| --- | --- | --- | --- |
| unit | TODO | TODO | TODO |
| integration | TODO | TODO | TODO |

TODO: the quadrants covered, the regression suite, mutation testing, and flaky-test handling.

## Environments and matrix

<!-- The supported targets and versions (browsers, devices and OS versions, runtimes, hardware), the test data
     sources, and the test environments. Keep it to what the product supports and its analytics show. -->

| Target | Versions | Locales | Automated or manual |
| --- | --- | --- | --- |
| TODO: browser, device and OS, runtime | TODO | TODO | automated |

TODO: the test environments, and where the test data comes from.

## Risk register and coverage

<!-- The component's product risks. Each keeps its id for good: `R-<COMPONENT>-NN`, never reused. Priority: P0 (data
     loss, security, money, a user locked out), P1 (a core flow degraded), P2 (cosmetic or rare). Every P0 is covered
     by an automated test. Residual risk names the person who accepted it. A retired risk stays, struck through, with the
     change that retired it. -->

| Risk | Priority | Covered by | Residual risk, and who accepted it |
| --- | --- | --- | --- |
| R-TODO-01 TODO | P0 | SPEC-?/A? | none |

## Test catalog

<!-- Only the cases that sit outside every Spec's Acceptance: regression tests from fixes, characterization tests, and
     test-only additions. A Spec's own acceptance tests never go here, because the generated trace lists them. A
     test-only change adds one row, in the same commit. One row each: the case id, what it traces to (a risk id, an
     Acceptance id, or a standard's clause), the level, the test file, and the commit that added it. -->

| Case | Traces to | Level | Test file | Commit |
| --- | --- | --- | --- | --- |
| C-TODO-01 | R-TODO-01 | unit | tests/TODO | TODO |

## Traceability and evidence

<!-- Never a hand-typed matrix. Link the generated trace (`aidd new srs product`: Acceptance id, then test command,
     then commit) and the `aidd test` evidence for each head. -->

- Trace: `aidd new srs product`, which writes `.aidd/views/srs-product.md`.
- Evidence: `.aidd/evidence/` for the head, and the verification report on its PR/MR.

[spec]: {{spec_link}}
