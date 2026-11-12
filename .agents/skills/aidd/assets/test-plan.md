# Test plan: {{title}}

Spec: [{{spec}}][spec]. Written {{today}}. Frozen at Spec approval with the Spec and its tests. Feeds the component's living test plan: TODO (its path, or "none").

<!-- The verifier writes this plan, at the scope of one Spec (ISO/IEC/IEEE 29119-3, tailored). It says how each
     Acceptance id is proven, and what else this change must prove. Size it by route:
     - minor: none
     - normal: Scope and Test approach; the other sections, one line each
     - major, or compliance on: every section.
     The component's living plan (`aidd new test-plan <component> --living --spec {{spec}}`) holds the strategy, the
     environments, and the risk register. This plan states only its deviations and this change's own risks.
     Never restate what another file owns:
     - the Acceptance text (cite ids only) and the thresholds (the Spec's budget items, or the SLO)
     - the tests, their commands and `covers` (the Spec's `tests`), and the results (`aidd test` evidence)
     - the threats (the threat model, by id) and the rollout steps (the runbook).
     The Acceptance ids are the Spec's own (A1, A2, ...): never new and never renumbered. `aidd validate` warns when:
     - an id in Test approach is not in the Spec's `## Acceptance`
     - one of those is missing there
     - no test command `covers` one.
     Write the prose at the `instruction` level (the `aidd-team:plain-language` skill). -->

## Scope

<!-- The test items, what is in and out, and why (a platform, a locale, a load level). The test basis is the Spec's
     Acceptance, by link. Assumptions and constraints go here too. -->

TODO: in scope and out of scope.

## Risks

<!-- The product risks this change adds, ranked, each mapped to Acceptance ids. Cite the tech spec's pre-mortem rows and
     the Spec's risk dimensions by name; do not copy them.
     - P0: data loss, security, money, a user locked out
     - P1: a core flow degraded
     - P2: a cosmetic or rare path.
     Every P0 maps to at least one automated Acceptance id. At the change that lands, the verifier folds these rows
     into the component's living plan. Normal: one line. -->

| Risk | Priority | Acceptance ids |
| --- | --- | --- |
| TODO | P0 | A1 |

## Test approach

<!-- One row per Acceptance id of the Spec. Level: unit, integration, contract, e2e, visual, or manual. A manual row
     names who checks it and how, and is never the only proof of a P0 risk. Technique is optional (boundary values,
     property-based, exploratory). Real or mocked: mock only what you do not own or cannot run in CI (a payment
     provider, a clock, the network). Never mock the code under test. Name each mock and the contract test or recorded
     fixture that keeps it honest. A database, queue, or cache you run is real at the integration level:
     use a throwaway container per test run, seeded by the tests, never a shared database.
     The command that proves an id is its `covers`, and red on base is `aidd test`'s record: type neither here. -->

| Acceptance id | Level | Real or mocked | Technique |
| --- | --- | --- | --- |
| A1 | unit | TODO: real or mocked | |

<!-- Regression and retest: which existing tests this change must keep green, and which it retests. Deviations from
     the component's living plan: what differs here, and why. -->

TODO: regression, retest, and deviations from the living plan; or "none".

## Non-functional checks

<!-- Each quality the change can break, and the check that proves it. The threshold is an Acceptance id or the SLO;
     never type a number here. Normal: only when one applies. -->

| Quality | Check | Acceptance id or SLO |
| --- | --- | --- |
| performance | TODO: a load test, a bundle-size threshold | A? |
| accessibility | TODO: the accessibility check the project runs | A? |

## Environments and data

<!-- Where the tests run, and the matrix delta from the living plan (a browser, a device and OS, a locale, a hardware
     target). Each row that is not automated is a manual run with a named owner. Then the data: where it comes from
     (factories, recorded fixtures, a seeded database), how it resets between tests, and that it holds no real
     personal data or secret. Then prerequisite test work: a fixture factory, a fake service, a seam in legacy code. It
     is written before Spec approval. Rollout verification (smoke, canary, rollback signal) is the runbook's: link it.
     Normal: one line. -->

| Environment or target | Versions | Purpose | Automated or manual |
| --- | --- | --- | --- |
| TODO: CI, a browser, a device and OS | TODO | TODO | automated |

TODO: the data and its reset; the prerequisite test work, or "none"; the runbook's path, or "no rollout beyond the merge".

## Entry, exit, and suspension

<!-- aidd's own rules hold for every plan. Entry is the Spec approved and each new-behavior test red on base. Exit is
     every Acceptance id green in its command on the head, no open P0 or P1 defect, and no test edited after Spec
     approval (a wrong test goes back to Specify). Add only what this change needs, and what stops testing and what
     lets it resume. Every P0 risk has an automated test; the manual rows are recorded in the verification report. -->

- Entry: the Spec approved and each new-behavior test red on base, TODO.
- Exit: every Acceptance id green on the head, no open P0 or P1 defect, TODO.
- Suspension and resumption: TODO, or "default".

## Manual and exploratory

<!-- Session-based charters: a mission, a time box, and what the verifier notes. A finding becomes a defect or a new
     Spec, never a silent fix. Only with manual rows.
     User acceptance is not planned here, because this plan is frozen. A client or business owner who accepts the
     change by hand (`manual_acceptance: true`) records it, id by id, in the living acceptance record (`aidd new acceptance`). -->

| Charter | Time box | Tester | Notes |
| --- | --- | --- | --- |
| Explore TODO with TODO to discover TODO | 60 min | TODO | |

## Reporting

<!-- The completion report is the verification report plus the head's `aidd test` evidence. Say where it lives (the
     PR/MR) and who signs it. Normal: one line. -->

TODO: who reads the report, where it lives, and who signs it.

## Audit additions

<!-- With compliance on, or for a regulator, an auditor, or a QA owner who signs off; delete the section otherwise
     (ISO/IEC/IEEE 29119-3, 7.2.4, 7.2.8, 7.2.9, and 7.2.10). -->

| Item | Holds |
| --- | --- |
| Stakeholders and communication | TODO: who is told what, and when |
| Staffing | TODO: the test lead and the testers, with their roles |
| Estimate | TODO: effort as a range |
| Schedule | TODO: environment ready, tests written, exit, with dates |

[spec]: {{spec_link}}
