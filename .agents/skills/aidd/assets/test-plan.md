# Test plan: {{title}}

Spec: [{{spec}}][spec]. Written {{today}}. Frozen at Spec approval with the Spec and its tests.

<!-- The audited or agency variant. By default, testing lives in the Spec's Acceptance and the tech spec's
     Test strategy (`aidd new tech-spec`). Write this plan only when someone needs a management document:
     - a regulator or an auditor
     - a QA owner who signs off
     - a device or browser matrix
     - a client's user acceptance test.
     The required-docs matrix then asks for it: a compliance dimension, the audited profile, a device path,
     `uat: true`, or 10 or more Acceptance items. It holds the information items of ISO/IEC/IEEE 29119-3 (scope,
     approach, environments, criteria, risks, reporting), without a file per item.
     Write the prose at the `ste-80` level (the `aidd-team:plain-language` skill).

     The Acceptance criteria below are the Spec's own items by id (A1, A2, ...): never new ones and never renumbered.
     `aidd validate` warns when:
     - an id here is not in the Spec's `## Acceptance`
     - one of those is missing here
     - no test command `covers` one. -->

## Scope

<!-- What this plan proves, and what it does not (a platform, a locale, a load level), each with why. -->

TODO: in scope and out of scope.

## Acceptance criteria

<!-- One row per Acceptance id of the Spec. The command's `covers` and `tests.files` say which command and file prove
     it. Red on base is `aidd test`'s record. Type neither that proof nor red on base here. Level: unit,
     integration, contract, e2e, visual, or manual. A manual row names who checks it and how, and is never the only
     proof of a P0 risk. -->

| AC | Behavior | Level | Real or mocked |
| --- | --- | --- | --- |
| A1 | TODO | unit | real |

## Levels

<!-- The mix, and why: what each level proves that the one below cannot. Mock only what you do not own or cannot run
     in CI (a payment provider, a clock, the network). Never mock the code under test. -->

| Level | What it proves | Real | Mocked |
| --- | --- | --- | --- |
| unit | TODO | TODO | TODO |
| integration | TODO | TODO | TODO |

## Environments and matrix

<!-- Where the tests run, and on what. Keep the matrix to what the product supports and the analytics show. Each row
     that is not automated is a manual run with a named owner. -->

| Environment | Purpose | Data | Owner |
| --- | --- | --- | --- |
| TODO: CI, staging, a device lab | TODO | synthetic | TODO |

| Target | Versions | Locales | Automated or manual |
| --- | --- | --- | --- |
| browser: TODO | TODO | TODO | automated |
| device and OS: TODO (iOS, Android) | TODO | TODO | manual |

## Entry and exit criteria

<!-- Entry: what must hold before testing starts (the build, the data, the environment). Exit: what must hold to stop
     testing and ask for Merge approval or the client's sign-off. -->

- Entry: TODO (the Spec approved, the tests written and red on base, the environment seeded).
- Exit: every Acceptance id green in its command, no open P0 or P1 defect, every manual row recorded, TODO.

## Non-functional

<!-- One row per quality the change can break, each with a threshold and the command that checks it. -->

| Quality | Threshold | Check |
| --- | --- | --- |
| performance | TODO: p95 under N ms, bundle under N KB | TODO |
| accessibility | WCAG 2.2 AA, axe clean per state | TODO |
| security | TODO | TODO |

## Fixtures and test data

<!-- Where the data comes from (factories, recorded fixtures, a seeded database), and how it is reset between tests.
     State that the test data holds no real personal data or secret. -->

TODO: the fixtures.

## Risks

<!-- What would hurt most if it broke, ranked:
     - P0: data loss, security, money, a user locked out
     - P1: a core flow degraded
     - P2: a cosmetic or rare path.
     Every P0 maps to at least one automated Acceptance id. -->

| Risk | Priority | Acceptance ids |
| --- | --- | --- |
| TODO | P0 | A1 |

## Manual and exploratory

<!-- Session-based charters: a mission, a time box, and what the tester notes. A finding becomes a defect or a new
     Spec, never a silent fix. -->

| Charter | Time box | Tester | Notes |
| --- | --- | --- | --- |
| Explore TODO with TODO to discover TODO | 60 min | TODO | |

<!-- User acceptance is not planned here, because this plan is frozen. A client or business owner who accepts the
     change by hand (`uat: true`) records it, id by id, in the living acceptance record (`aidd new acceptance`). -->

## Reporting

<!-- Who hears what, and when. The test summary at exit: what ran, what passed, the open defects and their priority,
     and the residual risk. Also state where it lives (the verification report, the PR/MR) and who signs it. -->

TODO: the summary, its readers, and where it lives.

## Audited additions (ISO/IEC/IEEE 29119-3)

<!-- For a regulator, an auditor, or a QA owner who needs the full test plan; delete the section otherwise. -->

### Suspension and resumption

TODO: what stops testing (a blocking defect, a broken environment, a data problem) and what must hold to resume.

### Staffing and roles

| Role | Person | Responsibility |
| --- | --- | --- |
| Test lead | TODO | owns this plan and the completion report |
| Tester | TODO | the manual rows and charters |

### Schedule

| Milestone | Date | Depends on |
| --- | --- | --- |
| TODO: environment ready | YYYY-MM-DD | TODO |

### Deliverables

TODO: the test completion report (the verification report and the gate record for the head), the defect log, and the
manual run records. Also state where each is kept.

## Definition of done

- Every Acceptance id above is in some test command's `covers`, and every `new_behavior` command fails on base and passes on head (`aidd test`).
- No test was edited after Spec approval; a wrong test went back to Specify.
- Every P0 risk has an automated test; manual rows and charters are recorded in the verification report; the exit criteria hold.

[spec]: {{spec_link}}
