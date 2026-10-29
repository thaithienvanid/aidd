---
id: embedded/zephyr
type: opinionated
fills: [embedded-automotive-industrial:rtos]
default: true
implements: embedded-automotive-industrial:HIL or simulation run
roles: [architect, developer, verifier, reviewer]
when_changed: [west.yml, "**/prj.conf", "**/*.conf", "**/Kconfig*", "**/*.overlay", "**/*.dts", "**/*.dtsi", "**/*.yaml", "**/*.c", "**/*.h", "**/CMakeLists.txt"]
why: "Zephyr is an RTOS of the Linux Foundation that supports hundreds of boards from one tree, with hardware in devicetree and features in Kconfig files. It runs its tests on the host with native_sim, so firmware has evidence before a board exists."
reviewed: "2026-10-22"
maturity: established
tool:
  name: zephyr
  registry: github
  package: zephyrproject-rtos/zephyr
version_policy: current_stable
checked_version: "4.4.2"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "4.4.2"
source: https://docs.zephyrproject.org/latest/releases/index.html
evidence: For most users, the recommended starting point is either the latest stable release or the current LTS release.
alternatives: [FreeRTOS, ESP-IDF, Embassy, NuttX]
status: active
enforced_by:
  - name: twister
    command: [west, twister, -T, tests, -p, native_sim, --inline-logs]
---

# Zephyr runs the firmware

It answers the rtos choice of `aidd-team:embedded-automotive-industrial`. Zephyr is under the Apache License 2.0.

## What the team does

- Use the workspace layout of Zephyr's example-application: `west.yml` at the root pins Zephyr to the tag `v<pin>`, next to `app/`, `boards/`, `lib/`, and `tests/`. Import only the modules the product needs with `name-allowlist`.
- Start a long-lived product on the LTS line instead, 3.7, which Zephyr supports until 2029-07-27. The latest stable line, 4.4, is supported until 2027-04-12. Zephyr 4.5 was still a release candidate on 2026-10-22.
- Keep the hardware in devicetree overlays and the features in `prj.conf` and Kconfig fragments, all in git. Never edit the tree west fetched.
- Pin the Zephyr SDK in CI: 1.0.1 was the newest on 2026-10-22. Pin `west` too, 1.5.0 then.
- Write tests with ztest under `tests/`, each with a `testcase.yaml` that lists `native_sim`, so twister builds and runs them as a host program.
- For code that reaches a peripheral, add a `qemu_*` platform or a Renode run, as the emulation choice says.
- Run Zephyr's static analysis hook, `-DZEPHYR_SCA_VARIANT=codechecker`, for clang-tidy's checks on the firmware build.

## What the gate runs

One `tests` entry runs twister over `tests/` on `native_sim`. A test that fails or does not build fails the change.
