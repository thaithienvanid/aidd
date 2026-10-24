---
id: embedded/esp-idf
type: opinionated
fills: [embedded-automotive-industrial:rtos]
implements: embedded-automotive-industrial:HIL or simulation run
roles: [architect, developer, verifier, reviewer]
when_changed: [sdkconfig.defaults, "sdkconfig.defaults.*", "**/CMakeLists.txt", "**/idf_component.yml", dependencies.lock, partitions.csv, "**/Kconfig*", "**/*.c", "**/*.h", "**/*.cpp", "**/pytest_*.py"]
why: "ESP-IDF is Espressif's own framework for ESP32 chips, on FreeRTOS, and its pytest plugin runs the same test on the host, on Espressif's QEMU, or on a board, so a change has evidence without hardware."
reviewed: "2026-10-22"
maturity: established
tool:
  name: esp-idf
  registry: github
  package: espressif/esp-idf
version_policy: current_stable
checked_version: "6.1"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "6.1"
source: https://docs.espressif.com/projects/esp-idf/en/latest/esp32/contribute/esp-idf-tests-with-pytest.html
evidence: To execute a pytest case in QEMU, add the @pytest.mark.qemu marker to the test function.
alternatives: [Zephyr on ESP32, Arduino core for ESP32, Embassy with esp-hal]
status: active
enforced_by:
  - name: qemu
    command: [sh, -c, "idf.py build && pytest -m qemu"]
---

# ESP-IDF runs the firmware on ESP32 chips

It answers the rtos choice of `aidd-team:embedded-automotive-industrial` for Espressif's chips. ESP-IDF is under the Apache License 2.0.

## What the team does

- Build in the `espressif/idf` container at the tag `v<pin>`, the newest stable release on 2026-10-22. Espressif supports each minor release for 30 months and recommends one in its 12-month service period for a new project.
- Commit `sdkconfig.defaults` with the target chip, `idf_component.yml`, and the component manager's `dependencies.lock`. Never commit a generated `sdkconfig`.
- Mark each pytest case for QEMU with `@pytest.mark.qemu`. Espressif's QEMU models the ESP32, ESP32-S3, and ESP32-C3, and Espressif does not support it, so keep the board run too.
- Run the logic that needs no peripheral on the `linux` target, ESP-IDF's host build, with `pytest --target linux`.
- Turn on Secure Boot v2, flash encryption, app rollback, and anti-rollback. A new image calls `esp_ota_mark_app_valid_cancel_rollback()` only after its self-test passes. Try the eFuse steps in QEMU first, because on a chip they cannot be undone.
- PlatformIO, under the Apache License 2.0, can drive the same build. Pin its platform version too.
- `idf.py clang-check` runs clang-tidy on the app, but Espressif still marks it as under development. Treat its findings as advice until then.

## What the gate runs

One `tests` entry builds the app and runs the pytest cases marked for QEMU. A failed case or a failed build fails the change.
