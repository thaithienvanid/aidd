---
id: embedded/lvgl
type: opinionated
fills: [embedded-automotive-industrial:mcu-gui]
default: true
implements: product-defaults:perf_budget
roles: [product-designer, developer, verifier, reviewer]
when_changed: ["**/lv_conf.h", "**/ui/**", "**/screens/**", "**/fonts/**", "**/*.c", "**/*.h", "**/*.png"]
why: "LVGL is a widely used open-source graphics library for microcontroller displays, it runs the same UI code on the host, and its Test module compares each rendered screen with a reference image in CI."
reviewed: "2026-10-22"
maturity: established
tool:
  name: lvgl
  registry: github
  package: lvgl/lvgl
version_policy: current_stable
checked_version: "9.6.0"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "9.6.0"
source: https://docs.lvgl.io/master/debugging/test.html
evidence: The Test module provides functions to emulate clicks, key presses, encoder turns, time passing, and compare the UI with reference images.
alternatives: [Slint, TouchGFX, Qt for MCUs]
status: active
---

# LVGL draws the display on a microcontroller

It answers the mcu-gui choice of `aidd-team:embedded-automotive-industrial`. LVGL is under the MIT license.

## What the team does

- Pin LVGL to the tag `v<pin>`, and keep one `lv_conf.h` in git.
- Give each screen a memory budget, in bytes of LVGL heap and draw buffer, in the Spec's Acceptance. Measure it on the host with `lv_test_get_free_mem()` before and after the screen loads.
- Build the UI for the host too. A host test turns on `LV_USE_TEST`, creates a test display at the product's resolution and colour format, and calls `lv_test_screenshot_compare()` for each screen. The reference PNGs live in git.
- Use the SDL driver for the desktop simulator a person runs while designing. CI needs no window, because the Test module renders to memory.
- Convert only the glyphs and sizes the product shows, with `lv_font_conv` and its `--range` or `--symbols`, and commit the converter's command with the output.
- Create a screen's objects when it loads, and never in a timer or a draw callback, so the render loop allocates nothing.
- Slint is the alternative where the team writes Rust or wants its markup. Its royalty-free licence excludes embedded systems, so a closed product uses it under the GPLv3 or a paid licence with a royalty per device. TouchGFX, free for ST's chips, and Qt for MCUs, a commercial product, tie the UI to one vendor.

## What the gate runs

No `tests` entry of its own. The screenshot and memory tests run inside the project's C or C++ test runner.
