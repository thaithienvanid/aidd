---
id: cpp/clang-tidy
type: opinionated
fills: [ci-pipeline:linter]
default: true
implements: enterprise-controls:Static analysis
roles: [developer, security-engineer, reviewer]
when_changed: [.clang-tidy, "**/.clang-tidy", CMakePresets.json, "**/*.c", "**/*.h", "**/*.cc", "**/*.cpp", "**/*.cxx", "**/*.hh", "**/*.hpp"]
why: "clang-tidy reads the code with the same front end as the Clang compiler, so its checks for bugs, misuse, and the C++ Core Guidelines see what the compiler sees. A checked-in .clang-tidy keeps them the same everywhere."
reviewed: "2026-10-22"
maturity: established
tool:
  name: clang-tidy
  registry: pypi
  package: clang-tidy
version_policy: current_stable
checked_version: "23.1.3"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "23.1.3"
source: https://clang.llvm.org/extra/clang-tidy/
evidence: The -warnings-as-errors= option upgrades any warnings emitted under the -checks= flag to errors (but it does not enable any checks itself).
alternatives: [Cppcheck, PVS-Studio, SonarQube for C and C++]
status: active
enforced_by:
  - name: lint
    command: [cmake, --workflow, --preset, lint]
---

# clang-tidy checks the C and C++ code

It answers the linter choice of `aidd-team:ci-pipeline` for C and C++. clang-tidy is under the Apache License 2.0 with LLVM exceptions.

## What the team does

- Commit one `.clang-tidy` at the root. Enable named groups, such as `bugprone-*`, `cert-*`, `cppcoreguidelines-*`, `modernize-*`, and `performance-*`, and list each check the team turns off with its reason.
- Set `WarningsAsErrors: '*'`, so every enabled check fails the build.
- Add a `lint` configure preset that sets `CMAKE_C_CLANG_TIDY` and `CMAKE_CXX_CLANG_TIDY` to `clang-tidy`, and a `lint` workflow preset that builds with it. Each file is then checked with its real compile flags.
- Install the PyPI wheel at `pin` in CI, with `uv tool install clang-tidy==<pin>`, so the checks match on every machine.
- Run Cppcheck too, as a second pass, where the team wants checks clang-tidy lacks. It reads the same `compile_commands.json`.
- Turn off a check for one line with `NOLINT(<check>)` and a comment saying why, never for a whole file.

## What the gate runs

One `tests` entry runs the `lint` workflow preset. Any finding of an enabled check fails the change.
