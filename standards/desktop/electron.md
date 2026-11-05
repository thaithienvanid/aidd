---
id: desktop/electron
type: opinionated
fills: [desktop-apps:desktop-framework]
default: true
implements: desktop-apps:Electron fuse and preference check
roles: [developer, architect, security-engineer, reviewer]
when_changed: ["src/main/**", "src/preload/**", forge.config.ts, forge.config.js, package.json]
why: "Electron ships one Chromium and one Node.js with the app, so the desktop app renders the way the tested web front end does on macOS and Windows, and its security checklist and fuses are written down."
maturity: established
tool:
  name: electron
  registry: npm
  package: electron
version_policy: current_stable
checked_version: "45.0.0"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
citation:
  url: https://www.electronjs.org/docs/latest/tutorial/fuses
  quote: "You can validate the fuses that have been flipped or check the fuse status of an arbitrary Electron app using the @electron/fuses CLI."
alternatives: [Tauri, a native app for each platform]
status: active
lock_command: [pnpm, add, -D, electron, "@electron-forge/cli"]
enforced_by:
  - name: package
    command: [pnpm, exec, electron-forge, package]
---

# Electron builds the desktop app

It answers the desktop-framework choice of `aidd-packs:desktop-apps`. License: MIT for Electron, Electron Forge, and `@electron/fuses`.

A release that fixes a security advisory, such as 44.9.1 for GHSA-jr5w-w6x2-84p9, skips the release cooldown of the project's update bot.

## What the team does

- Add `electron`, and `@electron-forge/cli` and `@electron-forge/plugin-fuses` (8.0.1 here), as exact dev dependencies.
- Flip the fuses in the Forge fuses plugin with `strictlyRequireAllFuses: true`. A new Electron major that adds a fuse with no setting then fails the package step.
- Serve the app's pages over a custom protocol, never `file://`, and turn the `grantFileProtocolExtraPrivileges` fuse off.
- Hold every window to the Electron row of the pack's Implement step (S5). Write its preference test beside the window code, under the project's test runner.
- Stay on one of the three newest majors, the ones the Electron team supports.

## What the tests run

One `tests` entry runs `electron-forge package`. It fails when the app does not package, or when a fuse in the Electron binary has no setting. The pack's fuse and preference check then reads the packaged app.
