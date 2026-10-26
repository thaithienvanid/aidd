---
id: embedded/mcuboot-signed-updates
type: opinionated
fills: [embedded-automotive-industrial:firmware-update]
default: true
implements: embedded-automotive-industrial:Firmware signing test
roles: [architect, developer, security-engineer, reviewer]
when_changed: ["**/sysbuild.conf", "**/sysbuild/**", "**/mcuboot*.conf", "**/*.overlay", "**/*.dts", "**/pm_static.yml", "**/prj.conf"]
why: "MCUboot is a vendor-neutral secure bootloader with ports for Zephyr, NuttX, Mynewt, and Espressif chips, and it checks each image's signature, refuses an older security counter, and reverts a test swap that never confirms."
reviewed: "2026-10-22"
maturity: established
tool:
  name: mcuboot
  registry: github
  package: mcu-tools/mcuboot
version_policy: current_stable
checked_version: "2.4.0"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "2.4.0"
source: https://docs.mcuboot.com/design.html
evidence: Test swaps are supported to provide a rollback mechanism to prevent devices from becoming “bricked” by bad firmware.
alternatives: [the chip vendor's secure boot and bootloader, ESP-IDF's bootloader with Secure Boot v2]
status: active
---

# MCUboot boots only signed, newer firmware

It answers the firmware-update choice of `aidd-team:embedded-automotive-industrial`. MCUboot is under the Apache License 2.0.

## What the team does

- In Zephyr, build MCUboot and the app together with sysbuild and `SB_CONFIG_BOOTLOADER_MCUBOOT=y`. Use the MCUboot that the pinned Zephyr release fetches, or MCUboot `pin` on another RTOS.
- Sign with ECDSA P-256 or Ed25519. Keep the private key in the team's key store, never in git, and let only the release job sign. Never ship an image signed with the sample key that MCUboot provides for development.
- Give each image a version and a security counter with `imgtool sign --version` and `--security-counter`. Keep the counter in a trusted non-volatile place, so hardware downgrade prevention holds.
- Use a swap mode with a test swap. The new image confirms itself only after its self-test, so a crash on first boot reverts it.
- Make the bootloader immutable in the field, and turn on the chip's secure boot or readback protection beneath it.
- Prove the refusals in the emulation run, as the pack's firmware signing test asks.
- Publish an SBOM for each release from the firmware's build, such as Zephyr's `west spdx`. The SBOM's format and the scan belong to `aidd-team:enterprise-controls`. The CRA dates that make it a duty are in the pack's Dated obligations.

## What the gate runs

No `tests` entry of its own. The emulation standard's tests boot the signed, tampered, and older images, and they fail the change when one boots that should not.
