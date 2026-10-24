---
id: cpp/sanitizers
type: opinionated
fills: [test-design:undefined-behavior-check]
default: true
implements: secure-coding:Implement
roles: [developer, verifier, security-engineer, reviewer]
when_changed: ["**/*.c", "**/*.h", "**/*.cc", "**/*.cpp", "**/*.cxx", "**/*.hh", "**/*.hpp", "**/CMakeLists.txt", CMakePresets.json, project.yml]
why: "GCC and Clang ship AddressSanitizer and UndefinedBehaviorSanitizer, and running the whole test suite under them turns a buffer overflow, a use after free, or undefined behaviour that a plain run hides into a failed test."
reviewed: "2026-10-22"
maturity: established
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
source: https://clang.llvm.org/docs/AddressSanitizer.html
evidence: It consists of a compiler instrumentation module and a run-time library.
alternatives: [Valgrind Memcheck, MemorySanitizer on Clang]
status: active
enforced_by:
  - name: asan
    command: [cmake, --workflow, --preset, asan]
---

# The test suite runs under AddressSanitizer and UndefinedBehaviorSanitizer

It answers the undefined-behavior-check choice of `aidd-team:test-design` for C and C++. The sanitizers come with GCC and Clang, under their compilers' licences.

## What the team does

- Add an `asan` workflow preset that builds the tests with `-fsanitize=address,undefined -fno-sanitize-recover=undefined -fno-omit-frame-pointer -g` and runs them. Undefined behaviour then ends the run instead of printing a warning.
- Code that starts threads also gets a `tsan` preset with `-fsanitize=thread`. ThreadSanitizer cannot share a build with AddressSanitizer, so it is a run of its own.
- In a project that Ceedling tests, put the same flags in the test compiler and linker settings of `project.yml`.
- MSVC supports AddressSanitizer with `/fsanitize=address` but has no UndefinedBehaviorSanitizer, so run this preset with GCC or Clang.
- Suppress a finding only in a suppressions file in git, with the reason, and never by turning a sanitizer off.
- Firmware gets the same check on its host build. A sanitizer cannot run on the microcontroller itself.

## What the gate runs

One `tests` entry runs the `asan` workflow preset. A sanitizer report or a failing test fails the change.
