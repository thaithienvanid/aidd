+++
id = "typescript/maestro"
type = "opinionated"
fills = ["mobile-apps:mobile-ui-test"]
default = true
implements = "mobile-apps:UI tests on the OS matrix"
roles = ["tester", "developer", "reviewer"]
when_changed = [".maestro/**", "app/**", "src/**", "app.config.ts", "app.json"]
why = "Maestro drives the built app on a simulator, an emulator, or a device with short YAML flows, and EAS Workflows runs them in CI, so a flow test needs no native test code."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "established"
tool = { name = "maestro", registry = "github", package = "mobile-dev-inc/maestro" }
version_policy = "current_stable"
checked_version = "2.11.0"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
alternatives = ["Detox", "XCUITest", "Espresso"]
status = "active"
source = "https://docs.maestro.dev/"
evidence = "Maestro is the simplest and most effective framework for painless mobile and web UI automation using intuitive YAML flows."
enforced_by = [
  { name = "flows", command = ["maestro", "test", ".maestro"] },
]
+++

# Maestro runs the Expo app's UI flows

It answers the mobile-ui-test choice of `aidd-team:mobile-apps` for an Expo app.

## What the team does

- Keep one flow file per critical journey in `.maestro/`: sign up, sign in, the main purchase or action, and account deletion.
- Select elements by `testID` (`id:` in a flow), never by visible text that a translation changes.
- Run the flows against a `preview` build, on the OS matrix of the pack's UI tests row. EAS Workflows has a Maestro job for this.
- Install the Maestro CLI at one stated version in CI, the same on every runner.
- Give each flow its own test account or reset step, so a flow never depends on the one before it.
- Keep the screenshots and the recording of a failed flow as CI artifacts.

## What the gate runs

One `[[tests]]` entry runs `maestro test .maestro` against a running simulator or emulator. A failed flow fails the change.
