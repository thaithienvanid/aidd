---
name: test-design
description: "Practice skill: turn Acceptance into tests before code. Use in an aidd repository when writing or reviewing a Spec's tests, or someone asks what to test or says tests are flaky."
metadata:
  checked: "2026-10-22"
---

# Test design

**Use it when** you write a Spec's tests in Specify, or judge their strength in Review.

**Do not use when** the change under review *is* a test file the verifier wrote before Spec approval, which nobody may edit after; or to choose a test framework, which the repository already has.

## Standards

<!-- aidd:gen practice:test-design -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| ISTQB test design techniques (equivalence partitioning, boundary values, decision tables, state transitions) | CTFL v4.0.1, 2024 | 2026-10-16 | <https://istqb.org/certifications/certified-tester-foundation-level-ctfl-v4-0/> |
| ISO/IEC/IEEE 29119 (test conditions to test cases) | ISO/IEC/IEEE 29119-4:2021 | 2026-10-16 | <https://www.iso.org/standard/79430.html> |
| BDD and ATDD with Gherkin | — | 2026-10-16 (reviewed) | <https://cucumber.io/docs/gherkin/reference/> |
| The test pyramid, with consumer-driven contract tests between services | — | 2026-10-16 | <https://martinfowler.com/articles/practical-test-pyramid.html> |
| FIRST principles (fast, isolated, repeatable, self-validating, timely) | — | 2026-10-16 (reviewed) | — |
| Property-based testing and fuzzing for invariants and parsers | — | 2026-10-22 | <https://hypothesis.readthedocs.io/en/latest/> |
| Mutation testing to judge test strength | — | 2026-10-22 | <https://stryker-mutator.io/docs/> |
<!-- aidd:end -->

## Specify

- From each Acceptance line derive test conditions, then cases: equivalence partitions, boundary values, decision tables, state transitions. Where the Spec holds a decision table, read it as written: one test per row, its id in `covers`.
- Every `feat` or `fix` has at least one `new_behavior: true` test seen failing on the current code; a refactor keeps `new_behavior: false`.
- Tests are independent, deterministic, and fast, with the clock, seed, and time zone set. Fixtures are minimal, made up, never personal data, and named for what they set up; a test's name states the behavior and the condition.
- Each run gets its own database, schema, or namespace. When it cannot be made, the run fails with the reason, and never falls back to a shared or local one.
- At integration level, a database, queue, or cache the repository runs is real, not mocked: a throwaway container per run, seeded by the tests ([references/real-dependencies.md](references/real-dependencies.md)).
- Tests against production are read-only smoke tests; any write goes only to a dedicated test tenant or account that reporting, billing, and analytics exclude.
- Add the tests other specialists asked for: the threat model's abuse cases, the design's visual and accessibility tests, the AI thresholds' evals.
- Put the commands in `tests.commands` and the files, including test configuration the runner reads, in `tests.files`, for Spec approval to freeze.
- Test first by default. New code with nothing to break (type `feat`, no risk dimension, below major) may set `tests.mode: with_code`. Then you write the commands and a `covers` for every Acceptance id, and the developer writes the test files with the code.
- Test through the boundary: CLI, HTTP, files, UI. Assert identifiers, structure, and counts, never prose. Write one test per Acceptance condition, plus its abuse cases. Write the tests for open questions last.

## Review

- Would each test fail if the change were reverted or subtly wrong? Would it pass if only the wording changed? Does it test behavior, not implementation? Are error paths and boundaries covered? Surviving mutants name missing cases. Does a production-facing test write outside the test tenant?

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Property tests | invariants and parsers hold for generated inputs | Hypothesis, fast-check, or jqwik |
| Mutation run | the tests fail when the code is subtly wrong | a mutation tool, such as mutmut, Stryker, or PIT, failing below the team's score floor; the reviewer runs it after Implement |
| Flake check | a new test passes every time | the runner reruns each new test ten times; a retry never counts as green |
| Coverage and sanitizers | coverage holds its floor, and unsafe code shows no undefined behavior | the `coverage-tool` and `undefined-behavior-check` choices in CI |

- From `aidd-team:apis-and-services`: Contract tests.

## Stop if

- A `feat` or `fix` has no test seen failing on the current code.
- A test would pass on a shared or production store when its own cannot be made.
- A test mocks the dependency the Acceptance is about.

## Hand off

- Done: the test files and commands, red on base. Next: Spec approval, then the implementer. Needs: a runner or fixture the repository lacks. Stopped at: none, or the stop rule that fired.
