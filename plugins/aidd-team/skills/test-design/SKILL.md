---
name: test-design
description: "Practice skill: turn Acceptance into tests before implementation exists. Use when writing or reviewing a Spec's tests, or when someone says add tests, what should we test, test coverage, edge cases, the tests are flaky, the tests pass but the bug shipped, mutation testing, property-based tests, a test database, fixtures, or smoke tests: ISTQB techniques, one red-first test per new behavior, independent and deterministic tests that crash rather than share a database, read-only production checks, contract, property, visual, accessibility, and eval tests, and how to prove they are strong."
metadata:
  checked: "2026-09-28"
---

# Test design

**Use it when** you write a Spec's tests in Specify, or judge their strength in Review.

**Do not use when** the change under review *is* a test file the tester wrote before Spec approval, which nobody may edit after; and not for choosing a test framework, which the repository already decided. Writing a Spec's tests in Specify, and judging their strength in Review, are exactly what this is for.

## Standards

- ISTQB CTFL v4.0.1 test design techniques.
- ISO/IEC/IEEE 29119.
- BDD with Gherkin.
- The test pyramid with consumer-driven contract tests.
- FIRST (fast, isolated, repeatable, self-validating, timely).
- Property-based testing.
- Mutation testing.

## Specify, before Spec approval

- From every Acceptance line derive test conditions, then cases: equivalence partitions, boundary values, decision tables, state transitions.
- Every `feat` or `fix` has at least one `new_behavior = true` test seen failing on the current code; refactors keep `new_behavior = false`.
- Tests are independent, deterministic, and fast; fixtures are minimal and named for what they set up; a test name states the behavior and the condition.
- Each run gets its own database, schema, or namespace. When that isolated store cannot be created, the run crashes with the reason; it never falls back to a shared database, a developer's local one, or another run's schema, where it would pass on someone else's data or destroy it.
- Tests that run against production are smoke tests and read-only; any write goes only to a dedicated test tenant or account that reporting, billing, and analytics exclude.
- Add the tests the other specialists asked for: abuse cases from the threat model, visual and accessibility tests from the design, evals from the AI thresholds.
- Put the commands in `[[tests.commands]]` and the files, including test configuration the runner reads, in `tests.files`, so Spec approval freezes them.

## Test commands

- The repository suite; property tests (Hypothesis, fast-check, jqwik) for invariants and parsers; contract tests between services; a mutation run (mutmut, Stryker, PIT) named for the reviewer to run after Implement; a flake check that reruns new tests.

## Review

- Would each test fail if the change were reverted or subtly wrong? Does it test behavior, not implementation detail? Are error paths and boundaries covered? Surviving mutants name the missing cases.
- Does the setup fail loudly when its isolated store is missing, instead of falling back to a shared one? Does any production-facing test write outside the test tenant?

## Hand off

- Done: the test files and commands, red on base. Next: Spec approval, then the implementer. Needs: a runner or fixture the repository lacks. Stopped at: none, or the stop rule that fired.
