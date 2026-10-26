---
id: embedded/renode-emulation
type: opinionated
fills: [embedded-automotive-industrial:emulation]
default: true
implements: embedded-automotive-industrial:HIL or simulation run
roles: [developer, verifier, sre, reviewer]
when_changed: ["**/*.robot", "**/*.resc", "**/*.repl", "**/*.c", "**/*.h", "**/*.rs", "**/*.overlay", "**/*.dts", "**/prj.conf"]
why: "Renode runs the unchanged firmware binary on a model of the chip and its board, with peripherals, buses, and several devices at once, so an agent's change has evidence from CI before anyone flashes a board."
reviewed: "2026-10-22"
maturity: established
tool:
  name: renode
  registry: github
  package: renode/renode
version_policy: current_stable
checked_version: "1.17.0"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "1.17.0"
source: https://renode.readthedocs.io/en/latest/introduction/testing.html
evidence: Renode is integrated with the Robot Framework testing suite and provides user-friendly scripts for running tests.
alternatives: [QEMU, the RTOS's host build, the chip vendor's simulator]
status: active
enforced_by:
  - name: emulate
    command: [sh, -c, "renode-test tests/renode/*.robot"]
---

# Renode runs the firmware in CI without a board

It answers the emulation choice of `aidd-team:embedded-automotive-industrial`. Renode is under the MIT license.

## What the team does

- Keep a `.resc` script and, where the board is custom, a `.repl` platform file in `tests/renode/`, next to Robot Framework tests that load the built binary.
- Test what a person or a device sees: UART lines, GPIO states, and messages on the emulated bus. Each test sets its own timeout.
- Install Renode at `pin` in CI, from its release package or `antmicro/renode-test-action` with `renode-revision` set to the tag `v<pin>`. Never take `master`.
- Check that Renode models each peripheral the change touches. A peripheral it lacks gets a stub in the `.repl`, or the run moves to QEMU, and the Spec says which.
- Run the update path here too: boot a signed image, a tampered one, and an older one, and expect the bootloader to refuse the last two.
- Hardware-in-the-loop stays a separate step. It runs on a self-hosted runner wired to real boards, which the team owns and operates; an agent never starts it or changes it.

## What the gate runs

One `tests` entry runs every Robot test in `tests/renode/` with `renode-test`. A failed or timed-out test fails the change.
