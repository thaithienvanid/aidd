---
id: cpp/googletest
type: opinionated
fills: [ci-pipeline:test-runner]
default: true
implements: product-defaults:dev_basics
roles: [developer, verifier, reviewer]
when_changed: ["**/*.c", "**/*.h", "**/*.cc", "**/*.cpp", "**/*.cxx", "**/*.hh", "**/*.hpp", "**/CMakeLists.txt", CMakePresets.json, vcpkg.json]
why: "GoogleTest is a widely used C++ test framework with matchers and mocks, and CMake's CTest finds its tests one by one, so CI reports each failing test by name."
reviewed: "2026-10-22"
maturity: established
tool:
  name: googletest
  registry: github
  package: google/googletest
version_policy: current_stable
checked_version: "1.18.0"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "1.18.0"
source: https://google.github.io/googletest/primer.html
evidence: GoogleTest isolates the tests by running each of them on a different object.
alternatives: [Catch2, doctest, Boost.Test]
status: active
enforced_by:
  - name: test
    command: [cmake, --workflow, --preset, test]
---

# GoogleTest runs the C++ tests

It answers the test-runner choice of `aidd-team:ci-pipeline` for C++. GoogleTest is under the BSD 3-Clause license. Catch2, under the Boost Software License, is the alternative.

## What the team does

- Get GoogleTest at `pin` through vcpkg, or with `FetchContent` at the tag `v<pin>`. Link tests to `GTest::gtest_main` and register them with `gtest_discover_tests`, so CTest lists each test by name.
- Add a `test` workflow preset that configures, builds, and runs `ctest` with `--output-on-failure` and `--no-tests=error`. A suite that finds no tests then fails.
- The same tests run under the sanitizers of `cpp/sanitizers` and the coverage of `cpp/coverage`, through their own presets.
- Keep tests on the host. A test that needs hardware or a network gets its own CTest label, outside the `test` preset.

## What the gate runs

One `tests` entry runs the `test` workflow preset. A failing test, or a suite with no tests, fails the change.
