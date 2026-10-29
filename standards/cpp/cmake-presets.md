---
id: cpp/cmake-presets
type: opinionated
fills: [ci-pipeline:workspace]
default: true
implements: ci-pipeline:Reproducible build
roles: [developer, sre, reviewer]
when_changed: [CMakeLists.txt, "**/CMakeLists.txt", "**/*.cmake", CMakePresets.json, "**/*.c", "**/*.h", "**/*.cc", "**/*.cpp", "**/*.cxx", "**/*.hh", "**/*.hpp"]
why: "CMake is the build system most C and C++ projects and package managers support, and CMakePresets.json puts the CI build in a file, so CI and each machine configure, build, and test the same way."
reviewed: "2026-10-22"
maturity: established
tool:
  name: cmake
  registry: github
  package: Kitware/CMake
version_policy: current_stable
checked_version: "4.4.4"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "4.4.4"
source: https://cmake.org/cmake/help/latest/manual/cmake-presets.7.html
evidence: CMakePresets.json is meant to specify project-wide build details, while CMakeUserPresets.json is meant for developers to specify their own local build details.
alternatives: [Meson, Bazel, Make]
status: active
enforced_by:
  - name: build
    command: [cmake, --workflow, --preset, build]
---

# CMake presets build the C and C++ code with Ninja

It answers the workspace choice of `aidd-team:ci-pipeline` for C and C++. CMake is under the BSD 3-Clause license, and Ninja under the Apache License 2.0.

## What the team does

- Commit `CMakePresets.json` with a hidden base configure preset. It uses the `Ninja` generator, sets `CMAKE_EXPORT_COMPILE_COMMANDS`, and puts each preset's build in `build/${presetName}`. Keep `CMakeUserPresets.json` out of git.
- Turn warnings into errors in that base preset: `-Wall -Wextra -Wpedantic -Werror` for GCC and Clang, and `/W4 /WX` for MSVC. Silence one warning in the code that raises it, with a comment saying why.
- Add a `build` workflow preset that configures and builds. Other standards add `test`, `asan`, `coverage`, and `lint` the same way, so one command runs each step.
- Give each module its own target with `target_link_libraries`, and keep each target's headers private unless another module needs them.
- Set `cmake_minimum_required` to the oldest CMake the team supports, and install CMake at `pin` in CI. CMake 4 removed compatibility with versions older than 3.5.
- Pin Ninja in CI next to CMake. Ninja 1.13.2 was the newest release on 2026-10-22.

## What the gate runs

One `tests` entry runs the `build` workflow preset. A compile error, or any warning, fails the change.
