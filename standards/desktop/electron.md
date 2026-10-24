---
id: desktop/electron
type: opinionated
fills: [desktop-apps:desktop-framework]
default: true
implements: desktop-apps:Electron fuse and preference check
roles: [developer, architect, security-engineer, reviewer]
when_changed: ["src/main/**", "src/preload/**", forge.config.ts, forge.config.js, package.json]
why: "Electron ships one Chromium and one Node.js with the app, so the desktop app renders the way the tested web front end does on macOS and Windows, and its security checklist and fuses are written down."
reviewed: "2026-10-22"
maturity: established
tool:
  name: electron
  registry: npm
  package: electron
version_policy: current_stable
checked_version: "45.0.0"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
source: https://www.electronjs.org/docs/latest/tutorial/fuses
evidence: "You can validate the fuses that have been flipped or check the fuse status of an arbitrary Electron app using the @electron/fuses CLI."
pin: "44.9.1"
cooldown_until: "2026-10-28"
alternatives: [Tauri, a native app for each platform]
status: active
enforced_by:
  - name: package
    command: [pnpm, exec, electron-forge, package]
---

# Electron builds the desktop app

It answers the desktop-framework choice of `aidd-team:desktop-apps`. License: MIT for Electron, Electron Forge, and `@electron/fuses`.

Electron 45.0.0 came out on 2026-10-21, a major inside the cooldown of `aidd-team:dependency-upgrade`. `pin` holds 44.9.1, which fixes advisory GHSA-jr5w-w6x2-84p9, so it skips the cooldown. Move to 45 in a change of its own on the `cooldown_until` day.

## What the team does

- Add `electron` at `pin`, and `@electron-forge/cli` and `@electron-forge/plugin-fuses` (8.0.1 here), as exact dev dependencies.
- Flip the fuses in the Forge fuses plugin with `strictlyRequireAllFuses: true`. A new Electron major that adds a fuse with no setting then fails the package step.
- Serve the app's pages over a custom protocol, never `file://`, and turn the `grantFileProtocolExtraPrivileges` fuse off.
- Hold every window to the Electron row of the pack's Implement step (S5). Write its preference test beside the window code, under the project's test runner.
- Stay on one of the three newest majors, the ones the Electron team supports.

## What the gate runs

One `tests` entry runs `electron-forge package`. It fails when the app does not package, or when a fuse in the Electron binary has no setting. The pack's fuse and preference check then reads the packaged app.
