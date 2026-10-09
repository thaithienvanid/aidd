+++
id = "typescript/expo"
type = "opinionated"
fills = ["mobile-apps:mobile-framework"]
default = true
implements = "mobile-apps:Store SDK floors"
roles = ["architect", "developer", "reviewer"]
when_changed = ["package.json", "app.json", "app.config.ts", "app.config.js", "eas.json"]
why = "Expo builds the iOS and Android apps from one TypeScript code base: prebuild writes the native projects when a build needs them, and EAS builds and signs them, so a team without native specialists still ships to both stores."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "established"
tool = { name = "expo", registry = "npm", package = "expo" }
version_policy = "current_stable"
checked_version = "57.0.27"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
alternatives = ["Flutter", "React Native without Expo", "Swift and Kotlin, one app per platform"]
status = "active"
source = "https://docs.expo.dev/more/expo-cli/"
evidence = "It exits with non-zero in Continuous Integration (CI)."
enforced_by = [
  { name = "deps", command = ["npx", "expo", "install", "--check"] },
]
+++

# Expo builds the TypeScript mobile app

It answers the mobile-framework choice of `aidd-team:mobile-apps` for a team that writes TypeScript.

## What the team does

- Stay on the current Expo SDK, the `latest` release of the `expo` package. Move up one SDK at a time with `npx expo install expo@<next> --fix`, after you read that SDK's release notes. A beta SDK stays out of production.
- Use Continuous Native Generation. Keep `android/` and `ios/` out of the repository, and change native code only through `app.config.ts` and config plugins. `npx expo prebuild --clean` writes the native projects again from them.
- Build and sign with EAS Build. Keep the `development`, `preview`, and `production` profiles in `eas.json`, and the store credentials in EAS, never in the repository.
- Add a native package with `npx expo install`, so its version matches the SDK.
- Unit tests run under the project's `test-runner` choice. Jest needs the `jest-expo` preset, which mocks the native part of the Expo SDK.
- UI tests on a device follow the project's `mobile-ui-test` choice (`typescript/maestro` in the `ts-mobile` stack).

## What the gate runs

One `[[tests]]` entry runs `npx expo install --check`. In CI it exits non-zero when an installed package does not match the SDK, and that fails the change.
