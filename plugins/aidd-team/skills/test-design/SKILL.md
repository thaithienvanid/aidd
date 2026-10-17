---
name: test-design
description: "Practice skill: turn Acceptance into tests before code. Use in an aidd repository when writing or reviewing a Spec's tests, or someone asks what to test or says tests are flaky."
metadata:
  checked: "2026-09-30"
---

# Test design

**Use it when** you write a Spec's tests in Specify, or judge their strength in Review.

**Do not use when** the change under review *is* a test file the tester wrote before Spec approval, which nobody may edit after; or to choose a test framework, which the repository already has.

## Standards

<!-- aidd:gen practice:test-design -->
| Standard | Edition |
| --- | --- |
| ISTQB test design techniques (equivalence partitioning, boundary values, decision tables, state transitions) | CTFL v4.0.1, 2024 |
| ISO/IEC/IEEE 29119 (test conditions to test cases) | ISO/IEC/IEEE 29119-4:2021 |
| BDD and ATDD with Gherkin | — |
| The test pyramid, with consumer-driven contract tests between services | — |
| FIRST principles (fast, isolated, repeatable, self-validating, timely) | — |
| Property-based testing and fuzzing for invariants and parsers | — |
| Mutation testing to judge test strength | — |

Each standard's checked date and source are in the aidd-team roles reference (`references/roles.md` in `aidd-team:aidd-team`), section `aidd-team:test-design`.
<!-- aidd:end -->

## Specify

- From each Acceptance line derive test conditions, then cases: equivalence partitions, boundary values, decision tables, state transitions.
- Every `feat` or `fix` has at least one `new_behavior: true` test seen failing on the current code; a refactor keeps `new_behavior: false`.
- Tests are independent, deterministic, and fast; fixtures minimal and named for what they set up; a test's name states the behavior and the condition.
- Each run gets its own database, schema, or namespace; when it cannot be created, the run crashes with the reason, never falling back to a shared database, a developer's local one, or another run's schema.
- At integration level, a database, queue, or cache the repository runs is real, not mocked: a throwaway container per run, seeded by the tests ([references/real-dependencies.md](references/real-dependencies.md)). Mock only what you do not own or cannot run in CI.
- Tests against production are read-only smoke tests; any write goes only to a dedicated test tenant or account that reporting, billing, and analytics exclude.
- Add the tests other specialists asked for: the threat model's abuse cases, the design's visual and accessibility tests, the AI thresholds' evals.
- Put the commands in `tests.commands` and the files, including test configuration the runner reads, in `tests.files`, for Spec approval to freeze.
- Test first by default. New code with nothing to break (type `feat`, no risk dimension, below major) may set `tests.mode: with`. Then you write the commands and a `covers` for every Acceptance id, and the developer writes the test files with the code.
- Test through the boundary: CLI, HTTP, files, UI. Assert identifiers, structure, and counts, never prose. A frozen test that pins a sentence breaks on rewording. Write one test per Acceptance condition, plus its abuse cases. Write the tests for open questions last.

## Review

- Would each test fail if the change were reverted or subtly wrong? Would it pass if only the wording changed? Does it test behavior, not implementation? Are error paths and boundaries covered? Surviving mutants name missing cases.
- Does the setup fail loudly without its isolated store, rather than fall back to a shared one? Does a production-facing test write outside the test tenant?

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Property tests | invariants and parsers hold for generated inputs | Hypothesis (6.168.3), fast-check, or jqwik |
| Mutation run | the tests fail when the code is subtly wrong | `uvx mutmut==3.8.0 run`, `npx -p @stryker-mutator/core@10.0.0 stryker run`, or PIT, for the reviewer to run after Implement |
| Flake check | a new test passes every time | the runner reruns each new test several times; no retry counts as green |

- From `aidd-team:apis-and-services`: Contract tests.

## Stop if

- A `feat` or `fix` has no test seen failing on the current code.
- A test would pass on a shared or production store when its own cannot be made.
- A test mocks the dependency the Acceptance is about.

## Hand off

- Done: the test files and commands, red on base. Next: Spec approval, then the implementer. Needs: a runner or fixture the repository lacks. Stopped at: none, or the stop rule that fired.
