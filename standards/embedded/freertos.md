---
id: embedded/freertos
type: opinionated
fills: [embedded-automotive-industrial:rtos]
implements: ci-pipeline:Dependencies declared and locked
roles: [architect, developer, verifier, reviewer]
when_changed: ["**/FreeRTOSConfig.h", "**/CMakeLists.txt", "**/*.cmake", CMakePresets.json, "**/*.c", "**/*.h"]
why: "FreeRTOS is a small kernel that most microcontroller vendors ship in their SDKs. Its POSIX port runs the same tasks and queues as a host program, so a team on a vendor SDK keeps one kernel and still tests on the host."
reviewed: "2026-10-22"
maturity: established
tool:
  name: freertos-kernel
  registry: github
  package: FreeRTOS/FreeRTOS-Kernel
version_policy: current_stable
checked_version: "11.3.2"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "11.3.2"
source: https://github.com/FreeRTOS/FreeRTOS-Kernel
evidence: If using CMake, it is recommended to use this repository using FetchContent.
alternatives: [Zephyr, ESP-IDF, ThreadX]
status: active
---

# FreeRTOS runs the firmware on a vendor SDK

It answers the rtos choice of `aidd-team:embedded-automotive-industrial` where the chip vendor's SDK already brings FreeRTOS. The FreeRTOS kernel is under the MIT license.

## What the team does

- Get the kernel with CMake's `FetchContent` at the tag `V<pin>`, or as a git submodule at that tag. Never copy its files into the tree by hand.
- Keep one `FreeRTOSConfig.h` in git. Turn on `configCHECK_FOR_STACK_OVERFLOW`, `configASSERT`, and `configUSE_MALLOC_FAILED_HOOK`, and use static allocation where the safety analysis forbids a heap after start-up.
- For a long support period, the FreeRTOS LTS release is the alternative. Its 202406 LTS holds kernel V11.1.0.
- Build the firmware with CMake presets and a toolchain file that names the compiler. Pin that compiler in CI, such as an exact Arm GNU Toolchain release. Arm's download page refused an automated read on 2026-10-22, so the team reads the version there itself.
- Add a host preset that selects the `GCC_POSIX` port, so the tasks run as threads under the C test runner.
- The tests, the format, and the lint come from the `cpp/` standards the project adopts.

## What the gate runs

No `tests` entry of its own. The host tests of the C test runner, and the emulation run, prove the firmware's behavior.
