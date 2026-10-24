---
id: desktop/tauri
type: opinionated
fills: [desktop-apps:desktop-framework]
default: false
implements: desktop-apps:Signed update round trip
roles: [developer, architect, security-engineer, reviewer]
when_changed: ["src-tauri/**", package.json]
why: "Tauri runs the front end in the system's own webview with a Rust core, so the installer stays small, and each window reaches only the commands its capability file grants."
reviewed: "2026-10-22"
maturity: emerging
tool:
  name: tauri
  registry: npm
  package: "@tauri-apps/cli"
version_policy: current_stable
checked_version: "2.12.4"
checked: "2026-10-24"
checked_by: agent:claude-code/claude-opus-5-5
source: https://v2.tauri.app/security/capabilities/
evidence: "Capability files are either defined as a JSON or a TOML file inside the src-tauri/capabilities directory."
pin: "2.12.3"
cooldown_until: "2026-10-28"
alternatives: [Electron, a native app for each platform]
status: active
enforced_by:
  - name: build
    command: [pnpm, exec, tauri, build, --ci, --no-bundle]
---

# Tauri builds the desktop app

It answers the desktop-framework choice of `aidd-team:desktop-apps`, for an app where a small installer and a Rust core matter more than one Chromium on every platform. License: MIT or Apache-2.0, at your choice. `desktop/electron` stays the default. This choice is emerging: each system's webview renders the front end, so test it on each one you ship.

The CLI 2.12.4 and the `tauri` crate 2.12.5 came out on 2026-10-21, inside the cooldown of `aidd-team:dependency-upgrade`. So until `cooldown_until`, `pin` holds the CLI at 2.12.3, and the crate stays at 2.12.4.

## What the team does

- Add `@tauri-apps/cli` at `pin` and `@tauri-apps/api` as exact dev dependencies. Pin the `tauri` crate exactly in `src-tauri/Cargo.toml`, such as `tauri = "=2.12.4"`, and keep `Cargo.lock`.
- Hold each window to the Tauri row of the pack's Implement step (S6). Give it its own capability file under `src-tauri/capabilities/`, bound to its window label, never its title.
- Set the CSP in the Tauri configuration file, because Tauri turns its CSP protection on only from there.
- Make the update key with `tauri signer generate`. Keep the private key and its password in the CI secret store as `TAURI_SIGNING_PRIVATE_KEY` and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`, and only the public key in the repository. A lost key ends updates for every installed copy.

## What the gate runs

One `tests` entry runs `tauri build --ci --no-bundle`. It fails when the Rust core or the front end does not build. The pack's signed update round trip then proves the updater.
