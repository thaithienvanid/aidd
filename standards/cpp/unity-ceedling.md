---
id: cpp/unity-ceedling
type: opinionated
fills: [ci-pipeline:test-runner]
implements: product-defaults:dev_basics
roles: [developer, verifier, reviewer]
when_changed: [project.yml, "**/*.c", "**/*.h", "test/**"]
why: "Unity is a test framework in plain C that runs on a host or on a small microcontroller. Ceedling builds each test with CMock's generated mocks, so C and firmware logic is tested on the host without hardware."
reviewed: "2026-10-22"
maturity: established
tool:
  name: ceedling
  registry: github
  package: ThrowTheSwitch/Ceedling
version_policy: current_stable
checked_version: "1.2.0"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "1.1.10"
cooldown_until: "2026-10-28"
source: https://www.throwtheswitch.org/ceedling
evidence: Ceedling starts with the Unity test framework and CMock mock and stub generation, then adds a build system for coordinating, executing, and summarizing test and release builds.
alternatives: [Unity built by CMake and run by CTest, GoogleTest over C headers, CppUTest]
status: active
enforced_by:
  - name: test
    command: [ceedling, test:all]
---

# Unity and Ceedling run the C tests on the host

It answers the test-runner choice of `aidd-team:ci-pipeline` for C, and for firmware logic that has no C++. Unity, CMock, and Ceedling are under the MIT license. `cpp/googletest` stays the default for C++.

## What the team does

- Keep `project.yml` at the root, with the source and test paths and the host compiler. Ceedling builds the tests itself, so a firmware build system next to it is untouched.
- Write the logic that needs no peripheral as plain C modules, with each hardware access behind a header that CMock mocks.
- Build the tests with the flags of `cpp/sanitizers`, and measure them with the `gcov` plugin that `cpp/coverage` names.
- Install Ceedling at `pin` with `gem install ceedling -v <pin>`. Ceedling 1.2.0 came out on 2026-10-21, inside the 7-day cooldown, so `pin` stays at 1.1.10 until `cooldown_until`.

## What the gate runs

One `tests` entry runs `ceedling test:all`. A failing test, or a test that does not build, fails the change.
