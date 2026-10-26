---
id: cpp/coverage
type: opinionated
fills: [test-design:coverage-tool]
default: true
implements: test-design:Review
roles: [developer, verifier, reviewer]
when_changed: ["**/*.c", "**/*.h", "**/*.cc", "**/*.cpp", "**/*.cxx", "**/*.hh", "**/*.hpp", "**/CMakeLists.txt", CMakePresets.json, project.yml]
why: "gcovr turns the coverage that GCC's or Clang's own instrumentation records into one report with a line floor, so the coverage run is the test run the team already has."
reviewed: "2026-10-22"
maturity: established
tool:
  name: gcovr
  registry: pypi
  package: gcovr
version_policy: current_stable
checked_version: "8.7"
checked: "2026-10-24"
checked_by: agent:claude-code/claude-opus-5-5
pin: "8.7"
source: https://gcovr.com/en/stable/
evidence: Gcovr provides a utility for managing the use of the GNU gcov utility and generating summarized code coverage results.
alternatives: [llvm-cov with source-based coverage, lcov]
status: active
enforced_by:
  - name: coverage
    command: [sh, -c, "cmake --workflow --preset coverage && uvx gcovr@8.7 --root . --fail-under-line \"${COVERAGE_MIN_LINES:?set COVERAGE_MIN_LINES to the team floor, a percent of lines}\" build/coverage"]
---

# gcovr measures the coverage of the C and C++ tests

It answers the coverage-tool choice of `aidd-team:test-design` for C and C++. gcovr is under the BSD 3-Clause license.

## What the team does

- Add a `coverage` workflow preset that builds the tests with `--coverage` and no optimisation into `build/coverage`, and runs them.
- With Clang, pass `--gcov-executable "llvm-cov gcov"` to gcovr, so it reads Clang's data.
- Set `COVERAGE_MIN_LINES` in the CI environment to the team's floor, a percent of lines. aidd leaves the number to the team, so the check fails while the variable is unset.
- Raise the floor in its own change when coverage rises, and never lower it to let a change pass.
- Where a safety integrity level asks for branch or MC/DC coverage, measure it with the tool the safety case names. A line floor does not prove it.
- In a Ceedling project, turn on its `gcov` plugin, which reports through gcovr too.
- Run gcovr at `pin`.

## What the gate runs

One `tests` entry builds and runs the tests under coverage, then fails when line coverage is below `COVERAGE_MIN_LINES`, or while that variable is unset.
