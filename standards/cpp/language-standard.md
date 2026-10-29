---
id: cpp/language-standard
type: opinionated
fills: [ci-pipeline:language-version]
default: true
implements: product-defaults:dev_basics
roles: [architect, developer, reviewer]
when_changed: [CMakeLists.txt, "**/CMakeLists.txt", "**/*.cmake", CMakePresets.json]
why: "C++20 is the newest C++ every mainstream compiler supports in full with a stable ABI, and C17 is the newest C that GCC, Clang, MSVC, and the MISRA C rules all accept."
reviewed: "2026-10-22"
maturity: established
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
source: https://gcc.gnu.org/projects/cxx-status.html
evidence: Some C++20 features are available since GCC 8, but support was experimental and the ABI of C++20 features was not stable until GCC 16.
alternatives: [C++23 on GCC and Clang only, C23 on GCC 15 or Clang 18 and later, C++17 for an older toolchain]
status: active
---

# C++20 and C17 are the language versions

It answers the language-version choice of `aidd-team:ci-pipeline` for C and C++.

## What the team does

- Set the version once, in the top `CMakeLists.txt`: `set(CMAKE_CXX_STANDARD 20)`, `set(CMAKE_CXX_STANDARD_REQUIRED ON)`, and `set(CMAKE_CXX_EXTENSIONS OFF)`. For C, do the same with `CMAKE_C_STANDARD 17`.
- A library also states it on its target with `target_compile_features(<lib> PUBLIC cxx_std_20)`, so a project that links it gets at least that version.
- Pin the compilers in CI: GCC 16 or later, or a Clang and an MSVC that support every C++20 feature the code uses.
- Move to C++23 only when every compiler the project builds with supports it in full. On 2026-10-22, GCC called its C++23 support experimental, Clang called it partial, and MSVC offered only `/std:c++23preview`, which Microsoft says may not be ABI compatible across releases.
- Keep C at C17 for code that MSVC or a MISRA C checker reads. GCC 15 made C23 its default, so set the C version explicitly rather than rely on a compiler's default.
- Turn off compiler extensions, so code that builds on one compiler builds on the others.

## What the gate runs

No `tests` entry of its own. The build that `cpp/cmake-presets` runs fails when the code needs a newer version than the one set here.
